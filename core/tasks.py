import pymupdf
from PIL import Image
import pytesseract
from auth.models import User
from auth.quota import apply_quota_reset
from payments.billing import billable_pages, report_overage
import stripe
from datetime import datetime, timedelta
from uuid import uuid4
from payments.models import OverageReport
from payments.models import Plan, FREE_PLAN_ID
from keymanager.models import ApiUsage
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv
load_dotenv()

DB_URL = os.getenv("DB_URL")
engine = create_engine(DB_URL)
Session = sessionmaker(bind=engine)

PAGE_BREAK = "pagebreak_pagebreak"

OVERAGE_MAX_AGE = timedelta(days=30)


def report_pending_overage(session, user, plan, pages_before, added):
    now = datetime.now()
    billable = billable_pages(plan.quota_limit, pages_before, pages_before + added)
    if billable > 0:
        session.add(OverageReport(id=str(uuid4()), user_id=user.id, pages=billable, created_at=now, attempts=0))
        session.commit()

    pending = (
        session.query(OverageReport)
        .filter(OverageReport.user_id == user.id, OverageReport.sent_at.is_(None), OverageReport.expired.is_(False))
        .order_by(OverageReport.created_at)
        .all()
    )
    for report in pending:
        if now - report.created_at > OVERAGE_MAX_AGE:
            report.expired = True
            print(f"overage report {report.id} for user {user.id} expired unsent ({report.pages} pages)")
            continue
        if not user.stripe_customer_id:
            continue
        try:
            report_overage(os.getenv("STRIPE_SECRET_KEY"), user.stripe_customer_id, report.pages, report.id, report.created_at.timestamp())
            report.sent_at = datetime.now()
        except stripe.InvalidRequestError as e:
            if "already exists" in str(e):
                report.sent_at = datetime.now()
            else:
                report.attempts += 1
                report.last_error = str(e)[:255]
                print(f"overage report {report.id} rejected for user {user.id}: {e}")
        except stripe.StripeError as e:
            report.attempts += 1
            report.last_error = str(e)[:255]
            print(f"overage report {report.id} failed for user {user.id}: {e}")
    session.commit()


def extract_text(fp, user_id, usage_id=None):
    session = Session()
    try:
        with open(fp, 'rb') as f:
            doc = pymupdf.open(fp, filetype="pdf")
            
            user = session.query(User).get(user_id)
            if not user:
                return {"error": "User not found"}
            
            user_plan = session.query(Plan).get(user.plan_id)
            if apply_quota_reset(user, user.plan_id == FREE_PLAN_ID):
                session.commit()
            remaining=user_plan.quota_limit - user.master_quota
            status=""
            pages_to_process=0
            if user.plan_id == FREE_PLAN_ID:
                if remaining <=0:
                    status="error"
                    return {"error" : "Quota limit has been reached, Upgrade to a paid plan to process more pages", "status": status, "code": 429}
                if remaining < len(doc):
                    status="partial"
                    pages_to_process=remaining
                else:
                    status="complete"
                    pages_to_process=len(doc)
            else:
                status="complete"
                pages_to_process = len(doc)
            text = ""
            processed = 0
            try:
                for i in range(pages_to_process):
                    page=doc[i]
                    content = page.get_text()
                    if content:
                        processed+=1
                        text += content + PAGE_BREAK
                    else:
                        pix = page.get_pixmap(dpi=128)
                        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                        ocr_text = pytesseract.image_to_string(img, lang='eng')
                        if ocr_text:
                            text += ocr_text + PAGE_BREAK
                            processed+=1
                pages_before = user.master_quota
                user.master_quota += processed
                if usage_id is not None:
                    session.query(ApiUsage).filter(ApiUsage.id == usage_id).update({"pages": processed})
                session.commit()
                if user_plan.overage_cents_per_page > 0:
                    report_pending_overage(session, user, user_plan, pages_before, processed)
            except Exception as e:
                status="error"
                session.rollback() 
                return {"error": "An error occurred while processing the document, Try again.", "status":status, "code": 500}
            page_lst = text.split(PAGE_BREAK)[:-1]
            return {"text": page_lst, "pages_processed": processed, "status":status, "code": 200}
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()
        if os.path.exists(fp):
            os.remove(fp)