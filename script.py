def soma(a, b):
    return a + b

def subtracao(a, b):
    return a - b

def teste_operacoes():
    # Teste da soma
    res_soma = soma(2, 3)
    print(f"Testando soma(2, 3): {res_soma}")
    assert res_soma == 5
    
    # Teste da subtração
    res_sub = subtracao(10, 4)
    print(f"Testando subtracao(10, 4): {res_sub}")
    assert res_sub == 6
    
    print("Todos os testes passaram!")

if __name__ == "__main__":
    teste_operacoes()
