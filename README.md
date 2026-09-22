# UF Academic Briefing

**Canvas iCal → AWS Lambda → daily assignment email**

A small serverless project that downloads a **live** University of Florida Canvas calendar subscription, finds dated assignments from selected courses, and emails a briefing every day at **8:00 AM America/New_York**. It runs without a Canvas API token or an always-on computer.

Version 1 has been deployed and tested end-to-end: Lambda returned `{"statusCode":200,"sent":true,"assignment_count":3}`, CloudWatch recorded a successful send, and the email was received. That result was a snapshot from September 22, 2026, not a guarantee about future assignment counts.

## Features and default configuration

| Feature         | Default                                                            |
| --------------- | ------------------------------------------------------------------ |
| Classes         | COP5615 (`580049`), CDA6325C (`573643`), CAP5771 (`566428`)        |
| Calendar source | Fresh Canvas iCal feed fetched at each invocation                  |
| Events included | Canvas assignments only; ordinary calendar/lecture events excluded |
| Deadline window | Today plus the following 7 calendar days                           |
| Schedule        | Every day at 8 AM Eastern, respecting EST/EDT                      |
| Email           | HTML and plain text, via Amazon SES                                |
| Secrets         | Standard SSM Parameter Store `SecureString`                        |
| Runtime         | Python 3.12, 128 MB Lambda                                         |
| Infrastructure  | AWS SAM (`template.yaml`)                                          |

**Course-code detail:** The Canvas feed can label the graduate CDA6325C course as `CDA4324C`; this project matches its reliable Canvas course ID `573643` instead.

### Architecture

```text
EventBridge Scheduler (8 AM America/New_York)
               |
               v
           AWS Lambda ----> SSM Parameter Store: private iCal URL
               |
               v
     Download current Canvas .ics feed
               |
               v
    Filter UID=event-assignment-... and course IDs
               |
               v
         Find due dates in window
               |
               v
      Generate HTML + plain-text email
               |
               v
           Amazon SES ----> your verified inbox

CloudWatch Logs records runtime information and assignment counts.
```

## Important limitations and privacy

- **iCal is not a submission tracker:** an already submitted assignment can still appear. Grades and submission status are unavailable.
- Assignments without Canvas calendar dates cannot appear. Canvas may cap exported events.
- Date-only calendar events do **not** provide an exact cutoff time; the email labels these as `time not provided`. Open the assignment in Canvas for the authoritative deadline.
- The `.ics` export may contain private Zoom URLs or passcodes; the **subscription URL itself is a secret**. Do not post either to GitHub, issues, screenshots, or logs.
- `preview.py` uses a local downloaded `.ics` for testing; the deployed Lambda retrieves a live URL from Parameter Store instead. Do **not** upload the `.ics` to the SAM deployment bucket.
- `.gitignore` blocks the local calendar, `preview.html`, `response.json`, `samconfig.toml`, environment files, and SAM build output. It cannot undo files already committed; see the Git section below.

## Project files

```text
uf-academic-briefing/
├── .gitignore
├── README.md
├── LICENSE
├── template.yaml
├── preview.py
├── src/
│   ├── calendar_logic.py
│   └── lambda_function.py
└── tests/
    └── test_calendar_logic.py
```

The application uses the Python standard library for iCal parsing. AWS Lambda's Python managed runtime provides `boto3`; there is no `requirements.txt` or third-party dependency to install for Version 1.

---

# AWS deployment — start to finish

These instructions are written for **Arch Linux**, AWS region **`us-east-1`**, CLI profile **`uf-briefing`**, and an IAM user named **`kenet-developer`**. Replace these names if using your own setup. All services must be configured in the same intended AWS account and region. Do not deploy from an unrelated profile or from your AWS root account.

## 1. Set up AWS access and a cost alert

1. Create or choose an AWS account; enable MFA on both root and your developer IAM user. Use root for necessary account administration only.
2. In **Billing and Cost Management → Budgets**, create a small monthly cost budget with an email alert (e.g. $1). **A budget alerts; it is not a spending cap.**
3. Use an IAM user/group or IAM Identity Center identity for deployment. For this project's existing setup, the developer group has Lambda, CloudFormation, EventBridge, IAM, and CloudWatch Logs deployment permissions. SAM also needs deployment-bucket **S3** permissions; SES identity management permissions are needed if verifying email from this user. `SignInLocalDevelopmentAccess` is required for browser-based `aws login` from an IAM user. A broad development group is convenient for initial setup but should be tightened after deployment.
4. Grant your deployment identity `ssm:PutParameter` and `ssm:GetParameter` for the _specific_ parameter. To list parameters in the console, `ssm:DescribeParameters` is also useful. The Lambda execution role is **separate** and is configured by `template.yaml` to read that parameter and send an SES email.

Example **inline IAM policy for the developer identity** — replace `<AWS_ACCOUNT_ID>` with the account returned by `aws sts get-caller-identity` (do not copy an ID from another AWS account):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ManageUFCalendarSecret",
      "Effect": "Allow",
      "Action": ["ssm:PutParameter", "ssm:GetParameter", "ssm:DeleteParameter"],
      "Resource": "arn:aws:ssm:us-east-1:<AWS_ACCOUNT_ID>:parameter/uf-academic-briefing/calendar-url"
    },
    {
      "Sid": "DescribeSSMParameters",
      "Effect": "Allow",
      "Action": "ssm:DescribeParameters",
      "Resource": "*"
    }
  ]
}
```

You can create or edit this under **IAM → User groups → [developer group] → Permissions → Add permissions → Create inline policy**. Least-privilege deployment IAM policies will vary according to the SAM resource set and the deployment bucket. Avoid storing access keys in this repository.

AWS references:

- AWS CLI local console login: https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sign-in.html
- SAM deployment: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/using-sam-cli-deploy.html
- Parameter Store permissions: https://docs.aws.amazon.com/systems-manager/latest/userguide/parameter-store-setting-up.html

## 2. Install and verify local tools

Required: **AWS CLI v2**, **AWS SAM CLI**, Python (for local tests), plus `curl` and `unzip`. On x86-64 Arch Linux, the official CLI installers can be used as follows; if already installed, just run the version checks.

```bash
sudo pacman -S --needed curl unzip python git
aws --version
sam --version
python --version
```

Install AWS CLI if `aws` is missing:

```bash
cd ~/Downloads
curl -fsSL https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip -o awscliv2.zip
unzip awscliv2.zip
sudo ./aws/install
aws --version
```

Install SAM CLI if `sam` is missing:

```bash
cd ~/Downloads
curl -fL https://github.com/aws/aws-sam-cli/releases/latest/download/aws-sam-cli-linux-x86_64.zip -o aws-sam-cli-linux-x86_64.zip
unzip aws-sam-cli-linux-x86_64.zip -d sam-installation
sudo ./sam-installation/install
sam --version
```

If your computer is not x86-64, use the architecture-appropriate installers from the official AWS documentation instead:
https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html
https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html

## 3. Authenticate the _correct_ AWS identity

The existing project uses the profile name `uf-briefing`. Browser-based CLI login requires **AWS CLI v2.32.0 or later** and `SignInLocalDevelopmentAccess` for IAM users:

```bash
aws login --profile uf-briefing --region us-east-1
aws sts get-caller-identity --profile uf-briefing
```

**Check the output before deploying.** It should identify your intended developer IAM user (such as `...:user/kenet-developer`) in your intended account. It must **not** show `...:root` or the unrelated `...:user/Esep-Webhook` profile.

If the browser is stuck in the wrong session, log out and use a private browser window while signing in with your IAM-user account URL. A fresh authorization URL can also be generated with:

```bash
aws logout --profile uf-briefing
aws login --remote --profile uf-briefing --region us-east-1
aws sts get-caller-identity --profile uf-briefing
```

If AWS still selects unwanted environment credentials, inspect variable _names_ without printing credential values:

```bash
env | grep '^AWS_' | sed -E 's/=.*/=<set>/'
```

If the variables are set for an unrelated account, clear them in that shell and explicitly select your profile:

```bash
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
export AWS_PROFILE=uf-briefing
aws sts get-caller-identity
```

Always keep `--profile uf-briefing` on the commands below so another default profile cannot silently deploy to the wrong account.

## 4. Verify the receiving/sending email in SES

1. AWS Console → **Amazon Simple Email Service**; select `us-east-1`.
2. **Configuration → Verified identities → Create identity → Email address**.
3. Enter the address you want as **both sender and recipient**, then use the email verification link.
4. Confirm the identity status says **Verified** in `us-east-1`.

SES accounts in the sandbox can send to verified recipients, so sending to the same verified address is fine for a personal project. If the email is not verified, Lambda can run but SES can reject the send.

AWS reference: https://docs.aws.amazon.com/ses/latest/dg/verify-addresses-and-domains.html

## 5. Store the live Canvas subscription URL in Parameter Store

Get the link from **UF Canvas → Calendar → Calendar Feed**. Use the _subscription URL_, not a downloaded file path. If it starts with `webcal://`, replace that prefix with `https://` when entering it. The Lambda only accepts an HTTPS URL for `ufl.instructure.com`.

In **Bash**, enter the link without echoing it or placing it in your shell history:

```bash
read -rsp 'Canvas Calendar Feed subscription URL: ' CANVAS_URL; echo
aws ssm put-parameter \
  --name '/uf-academic-briefing/calendar-url' \
  --type SecureString \
  --tier Standard \
  --value "$CANVAS_URL" \
  --overwrite \
  --region us-east-1 \
  --profile uf-briefing
unset CANVAS_URL
```

For this project, use the default AWS-managed `aws/ssm` KMS key. If you use a custom KMS key instead, ensure the Lambda execution role can decrypt it and account for any added charges.

Confirm **metadata only**, without printing your private URL:

```bash
aws ssm get-parameter \
  --name '/uf-academic-briefing/calendar-url' \
  --query 'Parameter.[Name,Type,Version]' \
  --region us-east-1 \
  --profile uf-briefing
```

If this returns `AccessDeniedException` for `ssm:GetParameter`, fix the developer IAM/group policy for the parameter ARN in the **same AWS account** and retry. The parameter may already exist from an earlier root-user setup; no need to re-create it if it is in the correct account and region.

AWS reference: https://docs.aws.amazon.com/systems-manager/latest/userguide/secure-string-parameter-kms-encryption.html

## 6. Test locally (optional, but recommended)

Run these commands from the project folder:

```bash
python -m unittest discover -s tests -v
python preview.py /path/to/downloaded-calendar.ics
```

The preview writes `preview.html` into the current folder. Both the downloaded `.ics` and the preview are ignored by Git. You can pass an explicit preview date for repeatable comparisons, e.g. `python preview.py /path/to/downloaded-calendar.ics 2026-09-22`. **Local preview does not download the live URL or send email.**

## 7. Validate and deploy with SAM

From the folder containing `template.yaml`:

```bash
sam validate --template-file template.yaml
sam deploy --guided \
  --template-file template.yaml \
  --profile uf-briefing \
  --region us-east-1
```

**This Version 1 source has no external dependencies, so a separate `sam build` step is not required.** If you choose to run `sam build` on a machine without Python 3.12, SAM may complain that a matching build runtime is missing; the working initial deployment used the source-direct `sam deploy --guided` command shown above. For future dependencies, install Python 3.12 or use an appropriate `sam build --use-container` workflow.

Use these guided-deploy answers:

| Prompt                             | Value                                       |
| ---------------------------------- | ------------------------------------------- |
| Stack name                         | `uf-academic-briefing`                      |
| AWS Region                         | `us-east-1`                                 |
| `EmailAddress`                     | The address verified in SES                 |
| `SelectedCourseIds`                | `580049,573643,566428` (or selected subset) |
| `DaysAhead`                        | `7`                                         |
| Confirm changes before deploy      | `Y`                                         |
| Allow SAM CLI IAM role creation    | `Y`                                         |
| Disable rollback                   | `N`                                         |
| Save arguments to `samconfig.toml` | `Y`                                         |

SAM creates a managed **S3 deployment bucket** for application code and a CloudFormation stack containing the Lambda function, its IAM execution role, an EventBridge Scheduler schedule and its role, and a CloudWatch log group. It does _not_ upload your private local `.ics` file or the Canvas subscription URL.

At the changeset prompt, check you're deploying to the intended AWS account and `us-east-1`, then approve with `y`. A successful deployment prints `Successfully created/updated stack - uf-academic-briefing` and an output named `LambdaFunctionName`. The actual function name includes a generated suffix.

## 8. Send a manual test email

Get the deployed Lambda name without hardcoding its generated suffix:

```bash
FUNCTION_NAME=$(aws cloudformation describe-stacks \
  --stack-name uf-academic-briefing \
  --query "Stacks[0].Outputs[?OutputKey=='LambdaFunctionName'].OutputValue | [0]" \
  --output text \
  --region us-east-1 \
  --profile uf-briefing)
printf 'Lambda function: %s\n' "$FUNCTION_NAME"
```

Invoke it and examine the _actual Lambda response_ (a CLI invocation `StatusCode: 200` alone does not guarantee successful application execution):

```bash
aws lambda invoke \
  --function-name "$FUNCTION_NAME" \
  --payload '{}' \
  --cli-binary-format raw-in-base64-out \
  --region us-east-1 \
  --profile uf-briefing \
  response.json
cat response.json; echo
```

Expected shape, with a variable assignment count:

```json
{ "statusCode": 200, "sent": true, "assignment_count": 3 }
```

`sent: true` means SES accepted the send request; check your inbox (and junk folder) for actual delivery. If nothing is due in the next seven days, the app still sends an email with a count of zero.

Inspect the recent logs without revealing your secret:

```bash
aws logs tail "/aws/lambda/$FUNCTION_NAME" \
  --since 30m \
  --region us-east-1 \
  --profile uf-briefing
```

A normal log contains `Sent briefing: N upcoming assignments across 3 selected courses` and a `REPORT` with duration/memory. AWS Console alternatives: **Lambda → function → Test** using event `{}`, and **Lambda → Monitor → View CloudWatch logs**.

## 9. Verify the daily schedule

AWS Console → **EventBridge → Scheduler → Schedules**, in `us-east-1`, locate the schedule generated for `BriefingFunctionDailyAtEight` and confirm:

- **Enabled**
- `cron(0 8 * * ? *)`
- `America/New_York`
- Target is your Lambda function

The schedule runs daily at **8 AM Eastern** and automatically adjusts for daylight saving time. A successful manual invoke verifies the application; the first scheduled execution independently verifies the automation. You do not need to leave your computer on.

## 10. Edit, redeploy, and troubleshoot

For later deployments, re-authenticate if needed and use the **same profile**:

```bash
aws login --profile uf-briefing --region us-east-1
aws sts get-caller-identity --profile uf-briefing
sam deploy --template-file template.yaml --profile uf-briefing --region us-east-1
```

The guided deployment saves values in the locally ignored `samconfig.toml`. To change the verified email, `SelectedCourseIds`, or `DaysAhead`, use `sam deploy --guided ...` again or update your local SAM configuration and redeploy. To change the send time, edit `ScheduleExpression` in `template.yaml` then redeploy. If future courses are added, the comma-separated course IDs determine filtering; optionally update the friendly-name mapping in `src/lambda_function.py` (unknown IDs show as `Canvas course <id>`).

| Symptom                                        | What to check                                                                      |
| ---------------------------------------------- | ---------------------------------------------------------------------------------- |
| CLI says `user/Esep-Webhook`                   | Add `--profile uf-briefing` and verify `aws sts get-caller-identity`               |
| CLI says `...:root`                            | Log out; authenticate as the developer IAM user instead                            |
| `ssm:GetParameter` / `ssm:PutParameter` denied | Correct IAM policy, account ID, parameter name, and region                         |
| `cloudformation:CreateChangeSet` denied        | CLI is using wrong profile or deployment identity lacks CloudFormation permissions |
| SAM upload denied                              | Deployment identity needs access to the SAM S3 artifacts bucket                    |
| SES `MessageRejected`                          | Verify sender/recipient in SES **in `us-east-1`**, check sandbox restrictions      |
| `ParameterNotFound`                            | Create SSM parameter in the same account/region as Lambda                          |
| `Could not retrieve Canvas calendar feed`      | Check the stored subscription URL, connection, and Canvas feed availability        |
| Lambda invoke is `200` but no email            | Read `response.json` and the function's CloudWatch logs; check spam                |
| Assignment does not appear                     | Check selected course ID, actual Canvas calendar due date, and export limitations  |

## 11. Cost and teardown

At one invocation and one email per day, the workload is small: about 30 Lambda invocations, 30 Scheduler invocations, and 30 SES emails each month. Applicable AWS free allowances often cover Lambda, Scheduler, and small CloudWatch usage; SES, S3 artifacts, taxes, extra services, and other AWS account activity can create charges. Verify current prices in your AWS region and keep a Billing budget alert.

- https://aws.amazon.com/lambda/pricing/
- https://aws.amazon.com/eventbridge/pricing/
- https://aws.amazon.com/ses/pricing/

To **pause** daily mail, disable the schedule in EventBridge Scheduler. To **remove** the stack:

```bash
sam delete \
  --stack-name uf-academic-briefing \
  --region us-east-1 \
  --profile uf-briefing
```

The separately created **SSM parameter and SES verified identity are not part of the SAM stack**. Remove them separately if no longer needed. Check SAM deployment-bucket objects and AWS Budgets/CloudWatch resources as applicable.

---

# Git and publishing safely

Before committing, verify `.gitignore` exists in the **repository root** (same folder as `README.md` and `template.yaml`). Do not commit your downloaded Canvas file, subscription URL, test-email result, email preview, AWS credentials, SAM build output, or `samconfig.toml` (which may contain your email and deployment details).

```bash
git status --short
git check-ignore -v my-calendar.ics preview.html response.json samconfig.toml
```

On a new repo, initialize if needed, inspect staged changes, then commit:

```bash
git init                     # skip if already a Git repository
git add .
git diff --cached --stat
git diff --cached --check
git commit -m "Document AWS deployment and complete V1"
```

**If a secret file was already tracked**, `.gitignore` alone will not remove it from the Git index or past commits. Untrack it with `git rm --cached path/to/file`, and if the subscription URL or meeting credentials were exposed publicly, invalidate/rotate the affected secret and address Git history before publishing.
