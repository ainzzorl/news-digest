.PHONY: lambda-install-packages
lambda-install-packages:
	rm -rf package/
	poetry export -f requirements.txt --without-hashes > aws/requirements.txt
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

	(cd aws/function-dir; zip -r ../function.zip .)

.PHONY: lambda-deploy
lambda-deploy:
	aws --region us-west-2 lambda update-function-code --function-name news-digest-lambda --zip-file fileb://aws/function.zip

.PHONY: lambda-invoke
lambda-invoke:
	aws --region us-west-2 lambda invoke --function-name news-digest-lambda /dev/null
