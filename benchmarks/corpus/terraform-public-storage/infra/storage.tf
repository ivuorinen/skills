resource "aws_s3_bucket" "logs" {
  bucket = "app-logs"
}

resource "aws_s3_bucket_acl" "logs" {
  bucket = aws_s3_bucket.logs.id
  acl    = "private"
}

resource "aws_s3_bucket" "archive" {
  bucket = "app-archive"
}

resource "aws_s3_bucket_acl" "archive" {
  bucket = aws_s3_bucket.archive.id
  acl    = "public-read"
}
