import streamlit as st
import pandas as pd
import gspread
from datetime import datetime
import time
import pytz

# --- CONFIGURAÇÃO INICIAL ---
st.set_page_config(page_title="Distribuidor de Chamados", page_icon="🎫")

# --- CONEXÃO INTELIGENTE (CACHE DE RECURSO) ---
@st.cache_resource
def conectar_google_sheets():
    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = st.secrets["gcp_service_account"]
            client = gspread.service_account_from_dict(creds_dict)
        else:
            client = gspread.service_account(filename="credentials.json")

        # DICA: Se puder, troque o nome pelo ID da planilha para ser mais rápido
        # sheet = client.open_by_key("COLE_O_ID_DA_PLANILHA_AQUI")
        sheet = client.open("Sistema_Chamados") 
        return sheet
    except Exception as e:
        st.error("Erro ao conectar no Google! Espere 1 minuto e recarregue.")
        st.stop()

# --- LEITURA INTELIGENTE (CACHE DE DADOS - A SOLUÇÃO DO ERRO 429) ---
# O TTL=5 significa: "Só vá no Google se a última leitura foi há mais de 5 segundos"
@st.cache_data(ttl=5)
def carregar_dados_planilha():
    sh = conectar_google_sheets()
    try:
        aba = sh.worksheet("Chamados")
        dados = aba.get_all_records()
        return pd.DataFrame(dados)
    except Exception as e:
        # Se der erro de cota, retorna um DataFrame vazio para não quebrar tudo
        return pd.DataFrame()

# Carrega a conexão principal
sh = conectar_google_sheets()

try:
    # A aba de usuários muda pouco, então não precisa de cache agressivo
    aba_users = sh.worksheet("Colaboradores")
    # A aba de chamados usamos a função especial lá de cima
    aba_chamados = sh.worksheet("Chamados")
except:
    st.error("Erro ao achar as abas.")
    st.stop()

# --- FUNÇÃO HORA BRASIL ---
def hora_brasil():
    fuso = pytz.timezone('America/Sao_Paulo')
    return datetime.now(fuso).strftime("%d/%m/%Y %H:%M:%S")

# --- TELA DE LOGIN ---
if 'usuario' not in st.session_state:
    st.title("🎫 Login")
    try:
        lista_nomes = aba_users.col_values(1)[1:] 
    except:
        lista_nomes = []
    
    escolha = st.selectbox("Selecione seu nome:", [""] + lista_nomes)
    
    if st.button("Entrar no Sistema"):
        if escolha:
            st.session_state['usuario'] = escolha
            st.rerun()
        else:
            st.warning("Selecione um nome.")

# --- TELA PRINCIPAL ---
else:
    usuario = st.session_state['usuario']
    
    with st.sidebar:
        st.write(f"👤 **{usuario}**")
        if st.button("Sair"):
            del st.session_state['usuario']
            st.rerun()
    
    st.title(f"Olá, {usuario} 👋")
    st.divider()

    # AQUI ESTÁ O SEGREDO: Usamos a função com Cache
    df = carregar_dados_planilha()

    if df.empty:
        st.warning("⚠️ O sistema está lendo muitos dados ou a planilha está vazia. Aguarde alguns segundos...")
        if st.button("Tentar recarregar agora"):
            st.cache_data.clear() # Limpa o cache para forçar leitura
            st.rerun()
        st.stop()

    if 'Status' in df.columns and 'Responsavel' in df.columns:
        meu_chamado = df[
            (df['Status'] == 'Em Andamento') & 
            (df['Responsavel'] == usuario)
        ]
    else:
        st.error("Erro nas colunas da planilha.")
        st.stop()

    # --- CENÁRIO A: TEM CHAMADO ---
    if not meu_chamado.empty:
        dados = meu_chamado.iloc[0]
        numero_chamado = dados.get('Dados', 'N/A') 
        id_linha = dados.get('ID')
        
        st.info(f"Em atendimento: **Chamado {numero_chamado}**")
        
        if numero_chamado != 'N/A':
            link = f"https://frigelar.qualitorsoftware.com/html/hd/hdchamado/cadastro_chamado.php?cdchamado={numero_chamado}"
            st.link_button("🔗 Abrir no Qualitor", link)
        
        st.write("---")
        
        if st.button("✅ FINALIZAR", type="primary"):
            try:
                # Aqui limpamos o cache para garantir que vamos escrever na linha certa
                st.cache_data.clear()
                
                cell = aba_chamados.find(str(id_linha))
                linha = cell.row
                agora = hora_brasil()
                
                aba_chamados.update_cell(linha, 3, "Concluido")
                aba_chamados.update_cell(linha, 6, agora)
                
                st.success("Feito!")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")

    # --- CENÁRIO B: LIVRE ---
    else:
        pendentes = df[df['Status'] == 'Pendente']
        qtd = len(pendentes)

        st.metric("Fila de Espera", qtd)

        if qtd > 0:
            if st.button("📥 PEGAR PRÓXIMO"):
                # Limpa cache para garantir que ninguém pegou o chamado 1 segundo atrás
                st.cache_data.clear()
                
                # Recarrega direto da fonte (sem cache) para garantir
                dados_reais = aba_chamados.get_all_records()
                df_real = pd.DataFrame(dados_reais)
                
                fila = df_real[
                    (df_real['Status'] == 'Pendente') & 
                    (df_real['Responsavel'] == "")
                ]
                
                if not fila.empty:
                    primeiro = fila.iloc[0]
                    id_chamado = primeiro['ID']
                    
                    try:
                        cell = aba_chamados.find(str(id_chamado))
                        linha = cell.row
                        agora = hora_brasil()
                        
                        aba_chamados.update_cell(linha, 3, "Em Andamento")
                        aba_chamados.update_cell(linha, 4, usuario)
                        aba_chamados.update_cell(linha, 5, agora)
                        
                        st.toast("Chamado é seu!")
                        time.sleep(0.5)
                        st.rerun()
                    except:
                        st.error("Erro ao atribuir.")
                else:
                    st.warning("Alguém foi mais rápido!")
                    time.sleep(2)
                    st.rerun()
        else:
            st.success("Sem chamados na fila.")
            # Botão para atualizar a lista manualmente se a pessoa quiser ver se chegou algo
            if st.button("🔄 Atualizar Lista"):
                st.cache_data.clear()
                st.rerun()
