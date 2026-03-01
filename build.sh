#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt

# Criar diretórios necessários
mkdir -p data logs
