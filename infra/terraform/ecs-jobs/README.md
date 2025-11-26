# ECS Jobs Terraform

This directory is expected to contain Terraform configuration for ECS-based scheduled jobs. The deployment workflow imports existing EventBridge Scheduler schedules before applying changes to avoid conflicts when resources already exist in AWS.
