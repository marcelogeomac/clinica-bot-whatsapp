from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import json
import os
from datetime import datetime

app = Flask(__name__)

# Reutilizando o banco de dados JSON
diretorio_atual = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_JSON = os.path.join(diretorio_atual, "agendamentos.json")

# Dicionário temporário para saber em que parte do menu o usuario está
# Em produção usaremos um banco de dados para o "estado" do usuário
user_state = {}

def salvar_agendamentos(whatsapp_id, nome, data, especialidade):
    novo = {"paciente": nome, "especialidade": especialidade, "data": data, "id": whatsapp_id}
    dados = []
     
    # 1. Tenta ler os dados existentes primeiro (modo raw) 
    if os.path.exists(ARQUIVO_JSON):
        try:
            with open(ARQUIVO_JSON, "r", encoding="utf-8") as f:
                dados = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            dados = []
    
    # 2. Adiciona o novo agendamento à lista
    dados.append(novo)
    
    # 3. Agora grava a lista completa
    with open(ARQUIVO_JSON, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)
        
@app.route("/bot", methods=['POST'])
def bot():
    # Pega a mensagem e o número de quem enviou
    msg = request.values.get('Body', '').lower().strip()
    user_id = request.values.get('From', '')
    res = MessagingResponse()
    
    # Permite que o usuario escreva 'menu' para retornal ao principal caso se perca
    if msg == "menu":
        user_state[user_id]["step"] = "menu"
        res.message("Voltamos ao menu principal. Como podemos ajudar?\n1. Especialidades\n2. Pré-Agendar\n3. Meus agendamentos\n0. Sair")
        return str(res)
    
    # Se o usuario nao existe no dicionário, começa do início
    if user_id not in user_state:
        user_state[user_id] = {"step": "inicio"}
    
    # Lógica de Estados (Menu)
    state = user_state[user_id]["step"]
    
    if state == "inicio":
        res.message("Olá! Bem-vindo à Clínica Saúde & Bem-Estar Exercício. 🩺\nQual seu nome completo?")
        user_state[user_id]["step"] = "aguardando_nome"
    
    elif state == "aguardando_nome":
        user_state[user_id]["nome"] = msg
        user_state[user_id]["step"] = "menu"
        res.message(f"Olá {msg}! Como posso ajudar?\n1. Especialidades\n2. Agendar\n3. Meus agendamentos\n4. Cancelar\n0 Sair")
        print(f"Mensagem recebida: '{msg}' | Estado: {state}")
    
    elif state == "menu":
        if msg == "1":
            res.message("🩺 Temos: Cardiologia, Dermatologia e Clínica Geral.\n\nDigite 2 para agendar ou 3 para ver seus horários.")
            # Permanece o estado de "menu" para conseguir escolher outras opções
        elif msg == "2":
            user_state[user_id]["step"] = "escolhendo_especialidade"
            res.message("Escolha uma opção:\nA) Cardiologia\nB) Dermatologia\nC) Clínica Geral")
 
        elif msg == "3":
            # Chamada da função consulta
            agendamentos = consultar_agendamentos_whatsapp(user_id)
            res.message(agendamentos + "\n\nDigite 1, 2 ou 3 para continuar.")
            
        elif msg == "4":
            agendamentos = consultar_agendamentos_whatsapp(user_id)
            if "Não encontrei" in agendamentos:
                res.message(agendamentos + "\n\nDigite 2 para agendar algo novo.")
            else:
                user_state[user_id]["step"] = "cancelando"
                res.message(agendamentos + "\n\nQual o número do agendamento que deseja CANCELAR?")
        
        elif msg == "0":
            # Remover o usuário do dicionário memória
            user_state.pop(user_id, None)
            res.message("Atendimento encerrado. A Clínica Saúde & Bem-Estar agradace! Ser precisar de algo, é só dar um 'Oi'.")
        
        else:
            res.message("❌ Opção inválida. Por favor, digite apenas o número: 1, 2 ou 3.")
    
    elif state == "cancelando":
        resultado = cancelar_agendamento(user_id, msg)
        user_state[user_id]["step"] = "menu" # Retorna ao menu principal após cancelar_agendamento
        res.message(resultado + "\n\nO que deseja fazer agora?\n1. Especialidades\n2. Agendar\n3. Ver agendamentos\n4. Cancelar")

    
    elif state == "escolhendo_especialidade":
        opcoes = {"a": "Cardiologia", "b": "Dermatologia", "c": "Clínica Geral"}
        if msg in opcoes:
            user_state[user_id]["esp"] = opcoes[msg]
            user_state[user_id]["step"] = "aguardando_data"
            res.message(f"Para qual data deseja agendar {opcoes[msg]}? (Ex: 31/01)")
        else:
            res.message("Por favor, escolha A, B ou C.")
            
    elif state == "aguardando_data":
        nome = user_state[user_id]["nome"]
        esp = user_state[user_id]["esp"]
        salvar_agendamentos(user_id, nome, msg, esp)
        res.message(f"✅ Confirmado, {nome}!\nSua consulta de {esp} foi marcada para {msg}.")
        # Volta para o menu
        user_state[user_id]["step"] = "menu"
        res.message("Como posso ajudar agora?\n1. Especialidades\n2. Agendar\n3. Meus Agendamentos\n0. Sair")
       
    return str(res)

def consultar_agendamentos_whatsapp(user_id):
    if not os.path.exists(ARQUIVO_JSON):
        return "Você ainda não possui agendamentos."
    
    with open(ARQUIVO_JSON, "r", encoding="utf-8") as f:
        dados = json.load(f)
        
    # Filtra pelo ID do Whatsapp (From) para ser mais preciso que o nome
    meus = [a for a in dados if a.get('id') == user_id]
    
    if not meus:
        return "Não encontrei agendamentos para você."
    
    texto = "--- Seus agendamentos ---\n"
    for i, ag in enumerate(meus, 1):
        texto += f"{i}. {ag['especialidade']} - {ag['data']}\n"
    return texto

def cancelar_agendamento(user_id, indice_str):
    if not os.path.exists(ARQUIVO_JSON):
        return "Erro: Nenhum agendamento encontrado."
        
    try:
        indice  = int(indice_str) - 1 # converte "1" para o índice 0 da lista
        with open(ARQUIVO_JSON, "r", encoding="utf-8") as f:
            dados = json.load(f)
            
        # filtra os agendamentos do usuario para saber qual ele quer apagar
        meus = [a for a in dados if a.get('id') == user_id]
        
        if 0 <= indice < len(meus):
            item_para_remover = meus[indice]
            dados.remove(item_para_remover) # remove o item específico da lista
            
            with open(ARQUIVO_JSON, "w", encoding="utf-8") as f:
                json.dump(dados, f, indent=4, ensure_ascii=False)
            return "❌ Agendamento cancelado com sucesso!"
        else:
            return "⚠️ Número inválido. Não consegui cancelar."
          
    except ValueError:
        return "⚠️ Por favor, digite apenas o número da opção (ex: 1)."


if __name__ == "__main__":
    app.run(port=5000)


