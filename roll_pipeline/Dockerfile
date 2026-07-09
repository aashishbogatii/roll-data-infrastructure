FROM public.ecr.aws/lambda/python:3.13

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ENV ENV=prod

COPY . ${LAMBDA_TASK_ROOT}/roll_pipeline/

CMD ["roll_pipeline.lambda_handler.handler"]
