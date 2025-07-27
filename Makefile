.PHONY: lambda-install-packages
lambda-install-packages:
	rm -rf package/
	poetry export -f requirements.txt --without-hashes > aws/requirements.txt
	# Install grpc and regex with Linux platform
	pip install --platform manylinux2014_x86_64 --only-binary=:all: --target package/ grpcio==1.71.0 regex==2024.11.6
	# Install other dependencies
	pip install -r aws/requirements.txt -t package/

.PHONY: lambda-package
lambda-package:
	mkdir -p aws
	rm -rf aws/function.zip
	rm -rf aws/function-dir
	mkdir aws/function-dir

	cp scripts/*.py aws/function-dir
	cp -r news_digest aws/function-dir
	cp config.yml aws/function-dir
	cp session_name.session aws/function-dir
	cp -R package/* aws/function-dir

	# Remove macOS-specific binaries and other unnecessary files
	find aws/function-dir -name "*.dylib" -type f -delete  # macOS dynamic libraries
	find aws/function-dir -name "*.pyc" -type f -delete    # Python bytecode
	find aws/function-dir -name "__pycache__" -type d -exec rm -rf {} +  # Python cache
	find aws/function-dir -name "*.dist-info" -type d -exec rm -rf {} +  # Package metadata
	find aws/function-dir -name "*.egg-info" -type d -exec rm -rf {} +   # Package metadata

	(cd aws/function-dir; zip -r ../function.zip .)

.PHONY: lambda-deploy
lambda-deploy:
	aws --region us-west-2 lambda update-function-code --function-name news-digest-lambda --zip-file fileb://aws/function.zip

.PHONY: lambda-invoke
lambda-invoke:
	aws --region us-west-2 lambda invoke --function-name news-digest-lambda /dev/null

.PHONY: lambda-logs
lambda-logs:
	./scripts/lambda_logs.sh

.PHONY: test
test:
	python -m unittest discover tests
