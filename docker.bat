@echo off
set DOCKER_DIR=deploy

if "%1"=="" goto up
if "%1"=="build" goto build
if "%1"=="up" goto up
if "%1"=="down" goto down
if "%1"=="logs" goto logs
if "%1"=="clean" goto clean
if "%1"=="restart" goto restart
goto help

:build
docker-compose -f %DOCKER_DIR%/docker-compose.yml build
goto end

:up
docker-compose -f %DOCKER_DIR%/docker-compose.yml up -d
goto end

:down
docker-compose -f %DOCKER_DIR%/docker-compose.yml down
goto end

:logs
docker-compose -f %DOCKER_DIR%/docker-compose.yml logs -f
goto end

:clean
docker-compose -f %DOCKER_DIR%/docker-compose.yml down -v
docker system prune -f
goto end

:restart
docker-compose -f %DOCKER_DIR%/docker-compose.yml down
docker-compose -f %DOCKER_DIR%/docker-compose.yml build
docker-compose -f %DOCKER_DIR%/docker-compose.yml up -d
goto end

:help
echo Usage: docker.bat [command]
echo Commands:
echo   build   - Build all images
echo   up      - Start all services
echo   down    - Stop all services
echo   logs    - View logs
echo   clean   - Remove all containers and volumes
echo   restart - Restart all services
goto end

:end