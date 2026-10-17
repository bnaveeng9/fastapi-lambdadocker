# fastapi-lambdadocker

## Run the API container locally

Build and start the API with Uvicorn:

```sh
docker compose up --build
```

The API is available directly at <http://localhost:9000>. For example:

```sh
curl http://localhost:9000/home
curl http://localhost:9000/numbers
curl http://localhost:9000/story/stream/home
```

Stop the container with Ctrl+C, or run `docker compose down`. The Docker image
retains its Lambda handler command for AWS deployments; Compose overrides it
locally to run Uvicorn.

## Deploy to AWS Lambda

The GitHub Actions workflow in `.github/workflows/deploy-lambda.yml` runs on
pushes to `main` and can also be started manually. It creates the ECR repository
if it does not exist, builds and pushes an image for the Lambda function's
architecture using Docker Image Manifest V2, Schema 2 with gzip-compressed
layers, verifies the manifest, config, and layer media types in ECR, updates
the existing Lambda function to that image, configures the HTTP API's `$default`
route as a Lambda proxy integration, and loads
parameters recursively from `/sst/passphrase/fastapi-lambdadocker/` into its
environment. Parameter names relative to that path become environment variable
names; nested path separators are replaced with underscores. For example,
`/sst/passphrase/fastapi-lambdadocker/API_TOKEN` becomes `API_TOKEN`.

Configure GitHub Actions with these variables, either at the repository level
or in each GitHub Environment used for deployment:

- `AWS_REGION`: AWS region containing ECR and the Lambda function.
- `HTTP_API_ID`: ID of the existing API Gateway HTTP API (for example,
  `ajazewyhdg`).
- `ECR_REPOSITORY`: ECR repository name to create or use.
- `LAMBDA_FUNCTION_NAME`: existing Lambda function using the container image
  package type.

Add `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` as repository secrets, or as
secrets in each deployment environment. For environment-scoped secrets, the
workflow uses `production` for pushes to `main` and the selected `dev` or
`production` environment for manual runs. The credentials must belong to a
dedicated IAM user with only the deployment permissions the workflow needs:
`sts:GetCallerIdentity`, `ecr:CreateRepository`,
`ecr:DescribeRepositories`, `ecr:BatchGetImage`, `ecr:GetAuthorizationToken`,
`ecr:BatchCheckLayerAvailability`, `ecr:InitiateLayerUpload`,
`ecr:UploadLayerPart`, `ecr:CompleteLayerUpload`, `ecr:PutImage`,
`ssm:GetParametersByPath`, `lambda:GetFunctionConfiguration`,
`lambda:UpdateFunctionCode`, `lambda:UpdateFunctionConfiguration`,
`lambda:GetPolicy`, `lambda:AddPermission`, `apigateway:GET`,
`apigateway:POST`, and `apigateway:PATCH`. Scope permissions to the selected
repository, API, the
`/sst/passphrase/fastapi-lambdadocker/*` SSM parameters, and function where AWS
supports it.

The workflow creates or updates a `$default` Lambda proxy route and ensures the
`$default` stage auto-deploys. That route forwards every request to FastAPI, so
FastAPI handles paths such as `/home`, `/numbers`, and
`/story/stream/home`. The story path returns the same JSON greeting as `/home`.
Set `HTTP_API_ID` to the API behind the public endpoint, then run the workflow
to apply the route configuration.

The Lambda function must already exist, and its execution role and ECR
repository permissions must allow Lambda to retrieve the image. SecureString
parameters are decrypted by the workflow credentials and added to the Lambda
environment; restrict access to both the IAM user and function. If the
parameters use a customer-managed KMS key, also grant the IAM user
`kms:Decrypt` on that key. Prefer short-lived OIDC role credentials when
possible; if using access keys, rotate them regularly and never commit them.
