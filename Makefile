PYTHON ?= $(if $(wildcard .venv/bin/python),$(CURDIR)/.venv/bin/python,/opt/homebrew/bin/python3)
DEST ?= $(HOME)/Applications
APP := $(DEST)/murdic.app
BIN := $(APP)/Contents/MacOS/murdic
SOURCES := $(wildcard mac/*.swift) $(wildcard dictate/*.py)

.PHONY: all run install test benchmark sample
all: install

$(BIN): $(SOURCES) mac/Info.plist Makefile scripts/build-app.py scripts/sign-local build/murdic.icns
	"$(PYTHON)" scripts/build-app.py "$(APP)" "$(PYTHON)"

build/murdic.icns: mac/assets/murdic.png scripts/build-icon
	mkdir -p build
	scripts/build-icon "$<" "$@"

run: install
	open "$(APP)"

install: $(BIN)
	codesign --verify --strict "$(APP)"

sample: build/sample.wav
build/sample.wav: tests/sample.py
	"$(PYTHON)" tests/sample.py "$@"

test: sample
	PYTHONDONTWRITEBYTECODE=1 "$(PYTHON)" -m unittest discover -s tests -v

benchmark: all sample
	"$(BIN)" --benchmark "$(CURDIR)/build/sample.wav"
