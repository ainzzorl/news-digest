.PHONY: format
format :
			 yapf --recursive --in-place scripts/

.PHONY: lint
lint :
			 pylint scripts/
