FROM public.ecr.aws/lambda/python:3.12

LABEL name="fastapi-lambdaimage"
LABEL maintainer="naveen"
LABEL version="1.0.0"

WORKDIR ${LAMBDA_TASK_ROOT}

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ${LAMBDA_TASK_ROOT}

CMD ["fastapi_lambdadocker.handler"]
