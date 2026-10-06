# Deploy

The AWS account id is not stored in this repo. The JSON files here contain the
placeholder `${AWS_ACCOUNT_ID}`:

- `task-definition.json`: rendered by `.github/workflows/deploy.yml` from the
  `AWS_ACCOUNT_ID` repository secret.
- `iam/trust.json`, `iam/policy.json`: one-time setup of the deploy role. Render
  them locally before passing them to the AWS CLI:

  ```bash
  export AWS_ACCOUNT_ID=<your account id>
  envsubst '${AWS_ACCOUNT_ID}' < deploy/iam/trust.json  > /tmp/trust.json
  envsubst '${AWS_ACCOUNT_ID}' < deploy/iam/policy.json > /tmp/policy.json
  aws iam create-role --role-name syncfit-github-deploy --assume-role-policy-document file:///tmp/trust.json
  aws iam put-role-policy --role-name syncfit-github-deploy --policy-name deploy-backend --policy-document file:///tmp/policy.json
  ```

Repository secrets required: `SYNCFIT_TOKEN`, `AWS_ROLE_ARN`, `AWS_ACCOUNT_ID`.
