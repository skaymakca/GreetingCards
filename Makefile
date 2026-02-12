.PHONY: run app clean

run:
	.venv/bin/python main.py

app:
	.venv/bin/pyinstaller -y --windowed --name="Greeting Cards" --collect-all tkinterdnd2 main.py

clean:
	rm -rf build dist *.spec
