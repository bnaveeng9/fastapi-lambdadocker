FROM public.ecr.aws/lambda/python:3.12

COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:1.1.0 /lambda-adapter /opt/extensions/lambda-adapter

LABEL name="fastapi-lambdaimage"
LABEL maintainer="naveen"
LABEL version="1.0.0"

WORKDIR ${LAMBDA_TASK_ROOT}

ENV AWS_LWA_INVOKE_MODE=response_stream \
    GOOGLE_OAUTH_INTERACTIVE=false \
    GOOGLE_TOKEN_FILE=/tmp/gmail-user-token.json

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ${LAMBDA_TASK_ROOT}

ENTRYPOINT ["python", "-m", "uvicorn"]
CMD ["fastapi_lambdadocker:app", "--host", "0.0.0.0", "--port", "8080"]
