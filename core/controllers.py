from keymanager.models import ApiKey, ApiUsage
from db.extensions import db
from hashlib import sha256
from flask import request, jsonify, make_response, render_template, session
from uuid import uuid4
from .tasks import extract_text
from .redis import ocr_queue
from rq.job import Job
from .redis import rd
from rq.exceptions import NoSuchJobError


def core_routes_init(app):

    @app.route("/extract", methods=["POST"])
    def extract_head():
        request_file=request.files.get("pdf")
        if not request_file:
            return make_response(jsonify({"error": "No file(s) attached"}), 400)    

        authorization_header=request.headers.get('Authorization')
        if not authorization_header:
            return make_response("No authorization header", 401)
        broken_header=authorization_header.split()
        key=broken_header[1] if (len(broken_header) == 2 and broken_header[0]=='Bearer') else None

        if key:
            query_hash= str(sha256(key.encode()).hexdigest())
            match=ApiKey.query.filter(ApiKey.key_hash==query_hash).first()
            if match:
                usage = ApiUsage(key_id=match.id, user_id=match.user_id)
                db.session.add(usage)
                db.session.commit()
                job_id=uuid4().hex
                temp_path = f"/tmp/{job_id}.pdf"

                request_file.save(temp_path)
                job = ocr_queue.enqueue(
                    extract_text,
                    temp_path,
                    match.user_id,
                    usage.id
                )
                return {
                    "job_id": job.id,
                    "status": "queued",
                    "message": "Processing started"
                }   
            else:
                return make_response("Invalid Key", 401)
        else:
            return make_response("Unauthorized", 401)
        
    @app.route('/status/<job_id>', methods=['GET'])
    def ocr_status(job_id):
        try:
            job = Job.fetch(job_id, connection=rd)

            if job.is_finished:
                return {
                    "result": job.result
                }
            elif job.is_queued:
                return {"status": "queued"}
            elif job.is_started:
                return {"status": "processing"}
            elif job.is_failed:
                return {"status": "failed"}, 500
            return {"status": job.get_status()}
        except NoSuchJobError:
            return {"status": "not_found"}, 404

    @app.route('/docs', methods=['GET'])
    def api_docs():
        return render_template('docs.jinja', is_authenticated=bool(session.get('email')))