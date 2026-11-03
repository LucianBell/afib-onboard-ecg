# Uso: conda activate afib-onboard  (ou: make PYTHON=/caminho/do/python ...)
PYTHON ?= python
SUBSET ?=
SUBSET_ARG := $(if $(SUBSET),--subset $(SUBSET),)

.PHONY: env data audit features train evaluate experiments export benchmark stream demo-data demo report reproduce test clean-interim

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

train:          ## experimento A, fase dev: CV no treino, escolha na validação (não abre o teste)
	$(PYTHON) scripts/exp_a.py dev

EVAL_FLAGS ?=
evaluate:       ## experimento A, fase test: exige escolha commitada; abre o teste uma vez (num clone: EVAL_FLAGS=--reproduce)
	$(PYTHON) scripts/exp_a.py test $(EVAL_FLAGS)

experiments:    ## experimentos B a I (regras fixadas no config; usam os artefatos do experimento A)
	$(PYTHON) scripts/experiments.py all

export:         ## exporta o modelo escolhido para models/ (JSON numpy + ONNX) com metadados
	$(PYTHON) scripts/export_model.py

benchmark:      ## latência, memória e tamanho na máquina atual (identificada); rode também no Pi
	$(PYTHON) scripts/benchmark.py

stream:         ## simulação do Pi recebendo o Holter, tempo acelerado, eventos JSON
	$(PYTHON) scripts/simulate_stream.py --velocidade 0 --so-alertas

demo-data:      ## pacote de replay do painel (data/demo/, fora do Git), a partir do teste do experimento A
	$(PYTHON) scripts/build_demo_pack.py

demo:           ## painel local (sem internet) em http://localhost:8501
	@test -f data/demo/demo_pack.npz || $(PYTHON) scripts/build_demo_pack.py || echo "sem dados: o painel usará ECG sintético"
	$(PYTHON) -m streamlit run app/dashboard.py

report:         ## figuras + README.md + MODEL_CARD.md gerados a partir de results/
	$(PYTHON) scripts/make_figures.py
	$(PYTHON) scripts/make_report.py

reproduce:      ## tudo do zero (SUBSET=N para um subconjunto rápido); num clone o teste A roda em modo reprodução
	$(if $(SUBSET),@echo "subconjunto de $(SUBSET) registros por base: README marcará n/d onde faltar dado",)
	AFIB_SUBSET=$(SUBSET) $(MAKE) data audit features train
	$(MAKE) evaluate EVAL_FLAGS=--reproduce
	AFIB_SUBSET=$(SUBSET) $(MAKE) experiments export benchmark demo-data report test

test:
	$(PYTHON) -m pytest -q tests

clean-interim:
	rm -rf data/interim
