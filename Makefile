# Uso: conda activate afib-onboard  (ou: make PYTHON=/caminho/do/python ...)
PYTHON ?= python
SUBSET ?=
SUBSET_ARG := $(if $(SUBSET),--subset $(SUBSET),)

.PHONY: env data audit features train evaluate report demo test clean-interim

env:            ## cria o ambiente conda fixado
	conda create -y -n afib-onboard python=3.12
	conda run -n afib-onboard python -m pip install -r requirements.lock

data:           ## baixa (com retomada), extrai e indexa as bases; cache da derivação I
	$(PYTHON) -m src.data all $(SUBSET_ARG)

audit:          ## gera docs/data_audit.md e results/audit/
	$(PYTHON) scripts/audit.py

features:       ## janelas pré-processadas, atributos, SQI e validação do detector de QRS
	$(PYTHON) scripts/build_features.py
	$(PYTHON) scripts/validate_qrs.py

train evaluate report demo:
	@echo "alvo '$@' ainda não implementado (ver ordem de trabalho em CLAUDE.md, seção 13)"; exit 1

test:
	$(PYTHON) -m pytest -q tests

clean-interim:
	rm -rf data/interim
