# Docker commands
DOCKER_DIR = deploy

.PHONY: docker-build docker-up docker-down docker-logs docker-clean docker-restart

docker-build:
	docker-compose -f $(DOCKER_DIR)/docker-compose.yml build

docker-up:
	docker-compose -f $(DOCKER_DIR)/docker-compose.yml up -d

docker-down:
	docker-compose -f $(DOCKER_DIR)/docker-compose.yml down

docker-logs:
	docker-compose -f $(DOCKER_DIR)/docker-compose.yml logs -f

docker-clean:
	docker-compose -f $(DOCKER_DIR)/docker-compose.yml down -v
	docker system prune -f

docker-restart: docker-down docker-build docker-up

# Production
docker-prod-build:
	docker-compose -f $(DOCKER_DIR)/docker-compose.prod.yml build

docker-prod-up:
	docker-compose -f $(DOCKER_DIR)/docker-compose.prod.yml up -d

docker-prod-down:
	docker-compose -f $(DOCKER_DIR)/docker-compose.prod.yml down