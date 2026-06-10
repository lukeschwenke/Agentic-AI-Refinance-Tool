
APP_NAME=Agentic_Refinance_Tool
IMAGE_NAME=agentic_refinance_tool_image
CONTAINER_NAME=agentic_refinace_tool_container
PORT=8000
PLATFORM=linux/amd64

AWS_REGION=us-east-1
AWS_ACCOUNT_ID=176276968777
ECR_REPO=datascience/agentic-ai-mortgage-refinance-tool
ECR_URI=$(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com/$(ECR_REPO)
IMAGE_TAG=latest

EC2_USER = ec2-user
EC2_INSTANCE_ID = i-084c4683b040ea62f
EC2_DIR = agentic_refi
NETWORK_NAME = refi_network
PROD_API_CONTAINER = agentic_refi_api
UI_CONTAINER = agentic_refi_ui
UI_PORT = 3000
PROXY_CONTAINER = agentic_refi_proxy
# Route53 record pointing at this EC2. Caddy obtains/renews the free
# Let's Encrypt certificate for it automatically — ports 80 and 443
# must be open in the instance's security group.
DOMAIN = refi-agentic-ai.lukeschwenke.com

build:
	docker buildx build \
		--platform $(PLATFORM) \
		-t $(IMAGE_NAME) \
		--load .

run:
	docker run -d \
		--name $(CONTAINER_NAME) \
		--env-file .env \
		-p $(PORT):8000 \
		$(IMAGE_NAME)

# Add this if testing DB logging locally
# -e AWS_PROFILE=default \
# -v $(HOME)/.aws:/root/.aws \

ui:
	poetry run streamlit run src/frontend/RefiAI_Main_Page.py

stop:
	docker stop $(CONTAINER_NAME) || true
	docker rm $(CONTAINER_NAME) || true

go: build run ui
rebuild: stop build run ui

# docker build -t refinance_tool .
# docker run --name refinance_api --env-file .env -p 8000:8000 refinance_tool


# -------- PUSH TO ECR --------

login-ecr:
	aws ecr get-login-password --region $(AWS_REGION) | \
	docker login --username AWS --password-stdin \
	$(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com

build-ecr:
	docker buildx build \
		--platform $(PLATFORM) \
		-t $(ECR_URI):$(IMAGE_TAG) \
		--push .

push-ecr: login-ecr build-ecr


# --------- CONNECT TO AWS EC2 AND PULL LATEST IMAGE (DEPLOY) ----------

login-ec2-and-pull:
	$(eval EC2_IP := $(shell aws ec2 describe-instances --instance-ids $(EC2_INSTANCE_ID) --region $(AWS_REGION) --query 'Reservations[0].Instances[0].PublicIpAddress' --output text))
	ssh-keygen -t rsa -f /tmp/ec2_deploy_key -N "" -q -f /tmp/ec2_deploy_key
	aws ec2-instance-connect send-ssh-public-key \
		--region $(AWS_REGION) \
		--instance-id $(EC2_INSTANCE_ID) \
		--instance-os-user $(EC2_USER) \
		--ssh-public-key file:///tmp/ec2_deploy_key.pub
	ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
		-i /tmp/ec2_deploy_key $(EC2_USER)@$(EC2_IP) "\
		 aws ecr get-login-password --region $(AWS_REGION) | docker login --username AWS --password-stdin $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com \
		 && docker system prune -f \
		 && docker pull $(ECR_URI):$(IMAGE_TAG) \
		 && docker network create $(NETWORK_NAME) 2>/dev/null || true \
		 && docker rm -f $(PROD_API_CONTAINER) 2>/dev/null; true \
		 && docker rm -f $(UI_CONTAINER) 2>/dev/null; true \
		 && docker rm -f $(PROXY_CONTAINER) 2>/dev/null; true \
		 && docker run -d --name $(PROD_API_CONTAINER) --network $(NETWORK_NAME) --env-file ~/$(EC2_DIR)/.env -p $(PORT):$(PORT) $(ECR_URI):$(IMAGE_TAG) \
		 && docker run -d --name $(UI_CONTAINER) --network $(NETWORK_NAME) --env-file ~/$(EC2_DIR)/.env \
		    -e API_BASE_URL=http://$(PROD_API_CONTAINER) -e API_PORT=$(PORT) \
		    $(ECR_URI):$(IMAGE_TAG) \
		    streamlit run src/frontend/RefiAI_Main_Page.py --server.address=0.0.0.0 --server.port=$(UI_PORT) \
		 && docker run -d --name $(PROXY_CONTAINER) --network $(NETWORK_NAME) \
		    -p 80:80 -p 443:443 \
		    -v caddy_data:/data -v caddy_config:/config \
		    caddy:2 \
		    caddy reverse-proxy --from $(DOMAIN) --to $(UI_CONTAINER):$(UI_PORT)"
	rm -f /tmp/ec2_deploy_key /tmp/ec2_deploy_key.pub

full-deploy-prod: push-ecr login-ec2-and-pull
