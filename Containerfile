# =============================================================================
# routing-live-view (image quay.io/sovereign-selfheal/routing-live-view).
# -----------------------------------------------------------------------------
# A live page of the routing decisions of the router and of the namespace labels of the demo.
# Quay builds this file on every git tag v* (build trigger): see README.md.
# Python packages: requirements.txt, exported from uv.lock with hashes (`uv export`).
# =============================================================================
# ubi9/python-312 (tag latest), resolved on registry.access.redhat.com on 2026-10-05
FROM registry.access.redhat.com/ubi9/python-312@sha256:a9f1c5dd1cd239c987058b0743c53af0378df48a12b6004bf4496847051062bf

WORKDIR /opt/app-root/src

COPY requirements.txt ./
RUN pip install --no-cache-dir --require-hashes --no-deps -r requirements.txt

COPY app ./app

# The base image runs as the non-root user 1001 (any UID with group 0 on OpenShift).
USER 1001
EXPOSE 8080
ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
