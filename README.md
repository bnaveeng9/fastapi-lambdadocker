"# fastapi-sample" 
"# fastapi-lambdadocker" 

## Run with Docker Compose

Build the image and start both local run modes:

```sh
docker compose up --build
```

The direct FastAPI/Uvicorn service is available at <http://localhost:8000>.
The Lambda service uses the AWS Lambda Runtime Interface Emulator on port 9000.
Invoke it by posting a Lambda event, such as an API Gateway event, to
<http://localhost:9000/2015-03-31/functions/function/invocations>.

To start just one mode, use `docker compose up --build web` for Uvicorn or
`docker compose up --build lambda` for Lambda emulation. Stop the services with
Ctrl+C, or run `docker compose down`.

## Deploy to AWS Lambda

The GitHub Actions workflow in `.github/workflows/deploy-lambda.yml` runs on
pushes to `main` and can also be started manually. It creates the ECR repository
if it does not exist, builds and pushes an image for the Lambda function's
architecture, updates the existing Lambda function to that image, and loads
parameters recursively from `/sst/passphrase/fastapi-lambdadocker/` into its
environment. Parameter names relative to that path become environment variable
names; nested path separators are replaced with underscores. For example,
`/sst/passphrase/fastapi-lambdadocker/API_TOKEN` becomes `API_TOKEN`.

Configure GitHub Actions with these variables, either at the repository level
or in each GitHub Environment used for deployment:

- `AWS_REGION`: AWS region containing ECR and the Lambda function.
- `ECR_REPOSITORY`: ECR repository name to create or use.
- `LAMBDA_FUNCTION_NAME`: existing Lambda function using the container image
  package type.

Add `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` as repository secrets, or as
secrets in each deployment environment. For environment-scoped secrets, the
workflow uses `production` for pushes to `main` and the selected `dev` or
`production` environment for manual runs. The credentials must belong to a
dedicated IAM user with only the deployment permissions the workflow needs:
`sts:GetCallerIdentity`, `ecr:CreateRepository`,
`ecr:DescribeRepositories`, `ecr:GetAuthorizationToken`,
`ecr:BatchCheckLayerAvailability`, `ecr:InitiateLayerUpload`,
`ecr:UploadLayerPart`, `ecr:CompleteLayerUpload`, `ecr:PutImage`,
`ssm:GetParametersByPath`, `lambda:GetFunctionConfiguration`,
`lambda:UpdateFunctionCode`, and `lambda:UpdateFunctionConfiguration`. Scope
permissions to the selected repository, the
`/sst/passphrase/fastapi-lambdadocker/*` SSM parameters, and function where AWS
supports it.
The Lambda function must already exist, and its execution role and ECR
repository permissions must allow Lambda to retrieve the image. SecureString
parameters are decrypted by the workflow credentials and added to the Lambda
environment; restrict access to both the IAM user and function. If the
parameters use a customer-managed KMS key, also grant the IAM user
`kms:Decrypt` on that key. Prefer short-lived OIDC role credentials when
possible; if using access keys, rotate them regularly and never commit them.
