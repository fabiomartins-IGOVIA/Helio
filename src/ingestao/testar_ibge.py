"""
testar_ibge.py
Teste inicial de conexão com a API pública do IBGE.
Objetivo: confirmar que conseguimos acessar a API e receber dados,
buscando a lista de municípios da Bahia.
"""

import requests  # biblioteca que faz a "conversa" com a API pela internet (HTTP)

# Endereço (endpoint) da API do IBGE que devolve os municípios da Bahia (UF = BA)
URL = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/BA/municipios"

# Faz o pedido à API usando o método GET ("me traga os dados deste endereço")
resposta = requests.get(URL)

# Todo pedido HTTP volta com um "código de status" que diz como foi:
# 200 = sucesso | 400 = pedido malformado | 404 = não encontrado
print(f"Código de status: {resposta.status_code}")

# Só seguimos se o pedido deu certo (código 200)
if resposta.status_code == 200:
    # Converte a resposta (texto em JSON) numa estrutura do Python (uma lista)
    municipios = resposta.json()

    # Mostra quantos municípios vieram e os primeiros nomes, como amostra
    print(f"Total de municípios recebidos: {len(municipios)}")
    print("Amostra (5 primeiros):")
    for municipio in municipios[:5]:
        print(f"  - {municipio['nome']}")
else:
    print("A requisição não teve sucesso. Verifique o endereço ou a conexão.")