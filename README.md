# Polly Text-to-Speech Pipeline

A serverless CI/CD pipeline built for **Pixel Learning Co.** that converts text to audio using Amazon Polly, stores the output in S3, and automates the entire process through GitHub Actions — with separate beta and production deployment workflows.

---

## Architecture Overview

```
speech.txt → GitHub Actions → Amazon Polly → example.mp3 → S3 Bucket
                  |
          Pull Request → deploy-beta → beta/example.mp3
          Merge to main → run_polly  → prod/example.mp3
```

**Services used:**
- Amazon Polly — text-to-speech conversion
- Amazon S3 — audio file storage
- GitHub Actions — CI/CD automation

---

## Prerequisites

- An AWS account with permissions for Polly and S3
- A GitHub account with access to this repository
- Python 3.x (used in the workflow runner)

---

## 1. AWS Setup

### Create your S3 Bucket

1. Log into the [AWS Console](https://console.aws.amazon.com)
2. Navigate to **S3 → Create Bucket**
3. Name your bucket and note the exact name — you'll need it for GitHub Secrets
4. Choose your region and leave default settings
5. Click **Create Bucket**

Your bucket will automatically organize files into two folders once the workflows run:
- `beta/` — files uploaded from pull requests via the `deploy-beta` job
- `prod/` — files uploaded after merging to main via the `run_polly` job

### Create an IAM User for GitHub Actions

1. Navigate to **IAM → Users → Create User**
2. Attach the following permissions policies:
   - `AmazonPollyFullAccess`
   - `AmazonS3FullAccess`
3. Go to **Security Credentials → Create Access Key**
4. Select **Application running outside AWS**
5. Save your `Access Key ID` and `Secret Access Key` — you'll need these in the next step

---

## 2. Configure GitHub Secrets

In your GitHub repo go to **Settings → Secrets and Variables → Actions → New Repository Secret** and add the following:

| Secret Name | Value |
|---|---|
| `AWS_ACCESS_KEY_ID` | Your IAM user access key ID |
| `AWS_SECRET_ACCESS_KEY` | Your IAM user secret access key |
| `AWS_REGION` | Your AWS region (e.g. `us-east-1`) |
| `S3_BUCKET_NAME` | Your S3 bucket name |

> **Note:** The `beta` and `prod` folder paths are hardcoded directly in the workflow files as `S3_Path: beta` and `S3_Path: prod` — they do not require secrets.

---

## 3. Modifying the Text

The text that Polly converts to speech lives in `speech.txt` at the root of the repository. Open the file and replace the contents with whatever you want converted to audio.

```
Welcome to Pixel Learning Co. This is your audio update for today.
```

Keep content under **3,000 characters** — this is the Amazon Polly limit for synchronous synthesis. For longer content the pipeline would need to be updated to use Polly's asynchronous `start_speech_synthesis_task` method.

---

## 4. Triggering the Workflows

This project uses two workflow files that trigger automatically based on your Git activity. No manual steps required.

### Beta Deployment — `on_pr.yml`

**Trigger:** Opening or updating a pull request targeting `main`

**Job:** `deploy-beta`

**What it does:**
1. Checks out the code
2. Configures AWS credentials from GitHub Secrets
3. Installs boto3 and runs `synthesize.py` to generate `example.mp3` via Polly
4. Uploads `example.mp3` to `s3://<your-bucket>/beta/example.mp3`

```yaml
- name: Convert txt to mp3 (beta)
  run: |
    pip install boto3 --upgrade
    python synthesize.py
    aws s3 cp example.mp3 s3://$S3_BUCKET_NAME/$S3_Path/example.mp3
```

To trigger this workflow:

```bash
git checkout -b my-feature-branch
# edit speech.txt
git add .
git commit -m "update speech content"
git push origin my-feature-branch
# open a pull request targeting main on GitHub
```

---

### Production Deployment — `on_merge.yml`

**Trigger:** Push to `main` (i.e. merging a pull request)

**Job:** `run_polly`

**What it does:**
1. Checks out the code
2. Configures AWS credentials from GitHub Secrets
3. Installs boto3 and runs `synthesize.py` to generate `example.mp3` via Polly
4. Uploads `example.mp3` to `s3://<your-bucket>/prod/example.mp3`

```yaml
- name: Convert txt to mp3 (prod)
  run: |
    pip install boto3 --upgrade
    python synthesize.py
    aws s3 cp example.mp3 s3://$S3_BUCKET_NAME/$S3_Path/example.mp3
```

Once you're satisfied with the beta output, merge the pull request on GitHub. The `run_polly` job triggers automatically on the push to main.

---

## 5. Verifying the Uploaded Files

### In the AWS Console

1. Navigate to **S3 → your bucket name**
2. You should see two folders: `beta/` and `prod/`
3. Click into either folder and select `example.mp3`
4. Click **Open** or **Download** to listen to the file

### Using the AWS CLI

```bash
# List files in beta
aws s3 ls s3://your-bucket-name/beta/

# List files in prod
aws s3 ls s3://your-bucket-name/prod/

# Download the prod file locally
aws s3 cp s3://your-bucket-name/prod/example.mp3 ./example.mp3
```

### Checking GitHub Actions Logs

1. Go to your repo → **Actions** tab
2. Click the most recent workflow run (`deploy-beta` or `run_polly`)
3. Expand the **Convert txt to mp3** step
4. Confirm you see `upload: ./example.mp3 to s3://...` with no errors

---

## Repository Structure

```
Polly_Text_to_Speech_Pipeline/
├── .github/
│   └── workflows/
│       ├── on_pr.yml        # Triggers deploy-beta job on pull request
│       └── on_merge.yml     # Triggers run_polly job on merge to main
├── synthesize.py            # Python script that calls Amazon Polly
├── speech.txt               # Text content to be converted
├── .gitignore
└── README.md
```

---

## Troubleshooting

**Workflow runs but no file appears in S3**
Check that all four GitHub Secrets are set correctly. A missing or misspelled secret will cause the upload to fail silently or land in the wrong location.

**`Invalid bucket name ""` error**
Your `S3_BUCKET_NAME` secret is empty or not defined. Verify it exists under Settings → Secrets and Variables → Actions.

**A file named `beta` or `prod` appears in the bucket root with no extension**
This is caused by a duplicate upload command missing the filename at the end. Each workflow should have only one upload line:
```bash
aws s3 cp example.mp3 s3://$S3_BUCKET_NAME/$S3_Path/example.mp3
```
Remove any second `aws s3 cp` line that ends without `/example.mp3` and delete the incorrectly named object from your S3 bucket.

**`run_polly` job shows success but no prod file in bucket**
Confirm `S3_Path: prod` is hardcoded in `on_merge.yml` — not pulling from a secret. If it was previously set to `${{ secrets.S3_PATH_PROD }}` and that secret didn't exist, the path resolved to an empty string and the upload had no destination.

**Polly synthesis fails**
Confirm your IAM user has `AmazonPollyFullAccess` attached and that your `AWS_REGION` secret matches the region your credentials are scoped to.

---

## Built With

- [Amazon Polly](https://aws.amazon.com/polly/)
- [Amazon S3](https://aws.amazon.com/s3/)
- [GitHub Actions](https://github.com/features/actions)
- [boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html)

---
