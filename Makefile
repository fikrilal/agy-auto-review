.PHONY: test install uninstall status clean

test:
	python3 -m unittest discover -s tests -p "test_*.py" -v

install:
	./install.sh

uninstall:
	./uninstall.sh

status:
	agy-review status

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
