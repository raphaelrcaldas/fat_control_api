# generate_pkce.py
import base64
import hashlib
import secrets


def create_pkce_code_challenge(code_verifier: str) -> str:
    """Cria um code_challenge a partir de um code_verifier usando S256."""
    sha256_hash = hashlib.sha256(code_verifier.encode()).digest()
    return base64.urlsafe_b64encode(sha256_hash).rstrip(b'=').decode()


# 1. Gerar um code_verifier aleatório e seguro
code_verifier = secrets.token_urlsafe(32)

# 2. Criar o code_challenge correspondente
code_challenge = create_pkce_code_challenge(code_verifier)

# 3. Imprimir os resultados
print('--- PKCE Codes ---')
print(f'Code Verifier: {code_verifier}')
print(f'Code Challenge: {code_challenge}')
print('-------------------------------')
print("\nGuarde o 'Code Verifier' para a requisição /token!")
