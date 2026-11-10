import pymupdf
from PIL import Image
import pytesseract
from auth.models import User
from payments.models import Plan, FREE_PLAN_ID
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv
load_dotenv()

DB_URL = os.getenv("DB_URL")
engine = create_engine(DB_URL)
Session = sessionmaker(bind=engine)

def extract_text(fp, user_id):
    session = Session()
    try:
        with open(fp, 'rb') as f:
            doc = pymupdf.open(fp, filetype="pdf")
            
            user = session.query(User).get(user_id)
            if not user:
                return {"error": "User not found"}
            
            user_plan = session.query(Plan).get(user.plan_id)
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
                pages_to_process = len(doc)
            text = ""
            processed = 0
            try:
                for i in range(pages_to_process):
                    page=doc[i]
                    content = page.get_text()
                    if content:
                        processed+=1
                        text += content + "pagebreak_pagebreak"
                    else:
                        pix = page.get_pixmap(dpi=128)
                        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                        ocr_text = pytesseract.image_to_string(img, lang='eng')
                        if ocr_text:
                            text += ocr_text
                            processed+=1
                user.master_quota += processed
                session.commit()
            except Exception as e:
                status="error"
                session.rollback() 
                return {"error": "An error occurred while processing the document, Try again.", "status":status, "code": 500}
            page_lst = text.split("pagebreak_pagebreak")
            return {"text": page_lst, "pages_processed": processed, "status":status, "code": 200}
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()
        if os.path.exists(fp):
            os.remove(fp)