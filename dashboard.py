import os
from groq import Groq
from dotenv import load_dotenv
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

load_dotenv()

# ── Configuração da Página
st.set_page_config(
    page_title="Dashboard - Carteira de Investimentos",
    page_icon="📊",
    layout="wide"
)

# ── Constantes
COLUNA_VALOR = {
    'Acoes_BR': 'Valor Atualizado',
    'ETF_BR': 'Valor Atualizado',
    'Fundo de Investimento': 'Valor Atualizado',
    'Renda Fixa_BR': 'Valor Atualizado CURVA',
    'Tesouro Direto': 'Valor Atualizado',
    'Acoes_EXT': 'Valor Atual (BRL)',
    'ETF_EXT': 'Valor Atual (BRL)',
    'Renda Fixa_EXT': 'Valor Atual (BRL)'
}

CLASSES_RENDA_FIXA = ['Renda Fixa_BR', 'Tesouro Direto', 'Renda Fixa_EXT']
CLASSES_RENDA_VARIAVEL = ['Acoes_BR', 'ETF_BR', 'Fundo de Investimento', 'Acoes_EXT', 'ETF_EXT']
ABAS_NACIONAIS = ['Acoes_BR', 'ETF_BR   ', 'Fundo de Investimento', 'Renda Fixa_BR', 'Tesouro Direto']
ABAS_INTERNACIONAIS = ['Acoes_EXT', 'ETF_EXT', 'Renda Fixa_EXT']

CORES_CLASSES = {
    'Acoes_BR': '#636EFA',
    'ETF': '#EF553B',
    'Fundo de Investimento': '#00CC96',
    'Renda Fixa': '#AB63FA',
    'Tesouro Direto': '#FFA15A',
    'Acoes_EXT': '#19D3F3',
    'ETF_EXT': '#FF6692',
    'Renda Fixa_EXT': '#B6E880'
}

GROQ_API_KEY = os.getenv('GROQ_API_KEY')
GROQ_MODEL = 'groq/compound'

# ── Funções de Carregamento
@st.cache_data

def carregar_dados(caminho_arquivo: str) -> dict[str, pd.DataFrame]:
    """Lê todas as abas do Excel consolidado."""
    return pd.read_excel(caminho_arquivo, sheet_name=None)


def obter_valor_total_aba(df: pd.DataFrame, col_valor: str) -> float:
    """Retorna a soma da coluna de valor de uma aba, ou 0 se não existir."""
    if col_valor in df.columns:
        return pd.to_numeric(df[col_valor], errors='coerce').sum()
    return 0.0


# ── Funções de Métricas
def calcular_patrimonio_total(abas: dict[str, pd.DataFrame]) -> float:
    total = 0.0
    for nome_aba, col_valor in COLUNA_VALOR.items():
        if nome_aba in abas:
            total += obter_valor_total_aba(abas[nome_aba], col_valor)
    return total


def calcular_distribuicao_classes(abas: dict[str, pd.DataFrame]) -> pd.DataFrame:
    registros = []
    for nome_aba, col_valor in COLUNA_VALOR.items():
        if nome_aba in abas:
            valor = obter_valor_total_aba(abas[nome_aba], col_valor)
            registros.append({'Classe': nome_aba, 'Valor': valor})
    return pd.DataFrame(registros)


def calcular_rf_vs_rv(df_classes: pd.DataFrame) -> pd.DataFrame:
    rf = df_classes[df_classes['Classe'].isin(CLASSES_RENDA_FIXA)]['Valor'].sum()
    rv = df_classes[df_classes['Classe'].isin(CLASSES_RENDA_VARIAVEL)]['Valor'].sum()
    return pd.DataFrame([
        {'Tipo': 'Renda Fixa', 'Valor': rf},
        {'Tipo': 'Renda Variável', 'Valor': rv}
    ])


def calcular_nacional_vs_internacional(abas: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Agrupa o valor total entre investimentos nacionais e internacionais."""
    nacional = sum(
        obter_valor_total_aba(abas[aba], COLUNA_VALOR[aba])
        for aba in ABAS_NACIONAIS if aba in abas
    )
    internacional = sum(
        obter_valor_total_aba(abas[aba], COLUNA_VALOR[aba])
        for aba in ABAS_INTERNACIONAIS if aba in abas
    )
    return pd.DataFrame([
        {'Tipo': 'Nacional', 'Valor': nacional},
        {'Tipo': 'Internacional', 'Valor': internacional}
    ])


def calcular_concentracao_produto(df: pd.DataFrame, col_valor: str) -> pd.DataFrame:
    """Retorna cada produto com seu valor e percentual dentro da classe."""
    df = df.copy()
    df[col_valor] = pd.to_numeric(df[col_valor], errors='coerce')
    total_classe = df[col_valor].sum()
    df['Percentual'] = (df[col_valor] / total_classe * 100).round(2)
    return df[['Produto', col_valor, 'Percentual']].sort_values(col_valor, ascending=False)


def calcular_top10(abas: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Une todos os produtos de todas as abas e retorna o Top 10 por valor."""
    todos = []
    for nome_aba, col_valor in COLUNA_VALOR.items():
        if nome_aba in abas and 'Produto' in abas[nome_aba].columns and col_valor in abas[nome_aba].columns:
            df_temp = abas[nome_aba][['Produto', col_valor]].copy()
            df_temp.columns = ['Produto', 'Valor']
            df_temp['Classe'] = nome_aba
            todos.append(df_temp)

    if not todos:
        return pd.DataFrame()

    df_all = pd.concat(todos, ignore_index=True)
    df_all['Valor'] = pd.to_numeric(df_all['Valor'], errors='coerce')
    return df_all.sort_values('Valor', ascending=False).head(10).reset_index(drop=True)


def normalizar_indexadores(abas: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Padroniza variações de capitalização nos indexadores."""
    mapa_normalizacao = {
        'PREFIXADO': 'Prefixado', 'prefixado': 'Prefixado', 'Prefixado': 'Prefixado',
        'IPCA': 'IPCA', 'ipca': 'IPCA',
        'CDI': 'CDI', 'cdi': 'CDI',
        'SELIC': 'Selic', 'selic': 'Selic',
    }
    abas_normalizadas = {}
    for nome_aba, df in abas.items():
        df = df.copy()
        if 'Indexador' in df.columns:
            df['Indexador'] = (
                df['Indexador']
                .astype(str)
                .str.strip()
                .apply(lambda x: mapa_normalizacao.get(x, x))
            )
        abas_normalizadas[nome_aba] = df
    return abas_normalizadas


def calcular_distribuicao_indexador(abas: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Agrupa o valor por indexador nas abas de Renda Fixa e Tesouro Direto."""
    frames = []
    for nome_aba in CLASSES_RENDA_FIXA:
        if nome_aba in abas:
            df = abas[nome_aba].copy()
            col_valor = COLUNA_VALOR[nome_aba]
            if 'Indexador' in df.columns and col_valor in df.columns:
                df[col_valor] = pd.to_numeric(df[col_valor], errors='coerce')
                frames.append(df[['Indexador', col_valor]].rename(columns={col_valor: 'Valor'}))

    if not frames:
        return pd.DataFrame()

    df_idx = pd.concat(frames, ignore_index=True)
    return df_idx.groupby('Indexador', as_index=False)['Valor'].sum().sort_values('Valor', ascending=False)


def calcular_cronograma_vencimentos(abas: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Agrupa o valor por ano de vencimento nas abas de Renda Fixa e Tesouro Direto."""
    frames = []
    for nome_aba in CLASSES_RENDA_FIXA:
        if nome_aba in abas:
            df = abas[nome_aba].copy()
            col_valor = COLUNA_VALOR[nome_aba]
            if 'Vencimento' in df.columns and col_valor in df.columns:
                df['Vencimento'] = pd.to_datetime(df['Vencimento'], errors='coerce')
                df[col_valor] = pd.to_numeric(df[col_valor], errors='coerce')
                df['Ano'] = df['Vencimento'].dt.year
                frames.append(df[['Ano', col_valor]].rename(columns={col_valor: 'Valor'}))

    if not frames:
        return pd.DataFrame()

    df_venc = pd.concat(frames, ignore_index=True)
    return df_venc.dropna(subset=['Ano']).groupby('Ano', as_index=False)['Valor'].sum().sort_values('Ano')


def formatar_moeda(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def gerar_comentario_ia(
    patrimonio_total: float,
    df_classes: pd.DataFrame,
    df_rf_rv: pd.DataFrame,
    df_top10: pd.DataFrame,
    df_nac_int: pd.DataFrame,
) -> str:
    try:

        if not GROQ_API_KEY:
            return "Erro: Chave API da Groq não configurada. Configure a variável GROQ_API_KEY."

        client = Groq(api_key=GROQ_API_KEY)

        # Monta resumo compacto da carteira para enviar ao modelo
        classes_txt = '\n'.join(
            f"  - {row['Classe']}: {formatar_moeda(row['Valor'])} "
            f"({row['Valor'] / patrimonio_total * 100:.1f}%)"
            for _, row in df_classes.iterrows()
        )

        rf = df_rf_rv[df_rf_rv['Tipo'] == 'Renda Fixa']['Valor'].values[0]
        rv = df_rf_rv[df_rf_rv['Tipo'] == 'Renda Variável']['Valor'].values[0]

        top10_txt = '\n'.join(
            f"  {i+1}. {row['Produto']} ({row['Classe']}): {formatar_moeda(row['Valor'])}"
            for i, row in df_top10.iterrows()
        )

        nac_int_txt = '\n'.join(
            f" - {row['Tipo']}: {formatar_moeda(row['Valor'])}"
            f"({row['Valor'] / patrimonio_total * 100:.1f}%)"
            for _, row in df_nac_int.iterrows()
        )

        prompt = f"""Você é um analista financeiro especializado em carteiras de investimento brasileiras.

CONTEXTO OBRIGATÓRIO — leia com atenção antes de analisar:

Definição exata de cada classe de ativo presente na carteira:
- Acoes_BR: Ações de empresas brasileiras negociadas na B3
- ETF: ETFs negociados na B3 (ex: IVVB11 replica o S&P 500 mas é custodiado no Brasil)
- Fundo de Investimento: FIIs — Fundos de Investimento IMOBILIÁRIO negociados na B3. Sempre chame de FIIs, nunca de "fundos de investimento" genericamente.
- Renda Fixa_BR: Renda fixa privada brasileira (CDBs, LCIs, LCAs)
- Tesouro Direto: Títulos públicos federais brasileiros (renda fixa pública nacional)
- Acoes_EXT: Ações internacionais custodiadas fora do Brasil
- ETF_EXT: ETFs internacionais custodiados fora do Brasil (ex: IVV é o ETF, não um ativo separado)
- Renda Fixa_EXT: Renda fixa pública internacional custodiada fora do Brasil

REGRAS ABSOLUTAS DE REDAÇÃO:
- Cada parágrafo deve conter UMA ideia diferente — nunca repita o mesmo raciocínio com outras palavras
- Nunca descreva os dados como se fossem conclusões (ex: "o Top 10 tem 10 posições" é uma tautologia proibida)
- Nunca cite o nome do produto E a classe como se fossem ativos distintos
- Nunca invente dados, percentuais ou comparações que não estejam nos dados abaixo
- Use sempre a terminologia exata definida no contexto acima
- Escreva em prosa corrida, sem tópicos, sem markdown, sem subtítulos

DADOS DA CARTEIRA:

Patrimônio total: {formatar_moeda(patrimonio_total)}

Alocação por classe de ativo:
{classes_txt}

Divisão de alocação nacional e internacional:
{nac_int_txt}

Renda Fixa total (Renda Fixa_BR + Tesouro Direto + Renda Fixa_EXT): {formatar_moeda(rf)} ({rf / patrimonio_total * 100:.1f}%)
Renda Variável total (Acoes_BR + ETF + Fundo de Investimento + Acoes_EXT + ETF_EXT): {formatar_moeda(rv)} ({rv / patrimonio_total * 100:.1f}%)

Top 10 maiores posições individuais (use para avaliar concentração, não para descrever):
{top10_txt}

ESTRUTURA OBRIGATÓRIA DA RESPOSTA — exatamente 4 parágrafos, nesta ordem:

Parágrafo 1 — Perfil da carteira: classifique como conservador, moderado ou arrojado e justifique com base na proporção renda fixa x renda variável e na presença de ativos internacionais.

Parágrafo 2 — Diversificação: avalie a qualidade da distribuição entre classes e entre mercados nacional e internacional. Seja específico sobre quais classes dominam e o que isso implica.

Parágrafo 3 — Concentração: analise se as maiores posições representam risco de concentração. Compare o peso das top posições em relação ao patrimônio total e aponte se alguma classe ou ativo individual tem peso desproporcional.

Parágrafo 4 — Balanço final: aponte UM ponto positivo concreto e UM ponto de atenção concreto, ambos baseados exclusivamente nos dados fornecidos. Não repita observações dos parágrafos anteriores."""

        message = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {'role': 'system', 'content': 'Você é um analista financeiro especializado em carteiras de investimento brasileiras. Sempre siga as instruções de estrutura e regras redacionais fornecidas pelo usuário.'},
                {'role': 'user', 'content': prompt}
            ],
            temperature=0.7,
            max_tokens=1024,
        )
        return message.choices[0].message.content

    except Exception as e:
        return f"Comentário indisponível: {str(e)}"

# ── Interface Principal
st.title("📊 Dashboard — Carteira de Investimentos")
st.divider()

with st.sidebar:
    st.header("Configurações")
    st.divider()
    arquivo = st.file_uploader(
    "Selecione o arquivo consolidado (.xlsx)",
    type=["xlsx"],
    help="Arquivo gerado pelo consolidador.py"
    )

    if arquivo is None:
        st.info("👆 Faça o upload do arquivo consolidado para visualizar o dashboard.")
        st.stop()

    if arquivo is not None:
        st.success("✅ Arquivo carregado!")
        st.divider()

        abas = carregar_dados(arquivo)
        abas = normalizar_indexadores(abas)
        patrimonio_total = calcular_patrimonio_total(abas)
        df_classes = calcular_distribuicao_classes(abas)
        df_rf_rv = calcular_rf_vs_rv(df_classes)
        df_top10 = calcular_top10(abas)
    
# ── Seção 1: Patrimônio Total

st.subheader("💰 Patrimônio Total")
col1, col2, col3 = st.columns(3)

with col1:
    st.metric(label="Patrimônio Líquido Total", value=formatar_moeda(patrimonio_total))

with col2:
    rf_total = df_rf_rv[df_rf_rv['Tipo'] == 'Renda Fixa']['Valor'].values[0]
    st.metric(label="Renda Fixa", value=formatar_moeda(rf_total))

with col3:
    rv_total = df_rf_rv[df_rf_rv['Tipo'] == 'Renda Variável']['Valor'].values[0]
    st.metric(label="Renda Variável", value=formatar_moeda(rv_total))

st.divider()

# ── Seção 2: Distribuição por Classe
st.subheader("🥧 Distribuição por Classe de Ativo")
col1, col2, col3 = st.columns(3)

with col1:
    fig_classes = px.pie(
        df_classes, names='Classe', values='Valor',
        title='Alocação por Classe', color='Classe',
        color_discrete_map=CORES_CLASSES, hole=0.45
    )
    total = df_classes['Valor'].sum()                                                           # ← linha 1
    rotulos = ['%{label}<br>%{percent}' if v / total >= 0.05 else '' for v in df_classes['Valor']]  # ← linha 2
    fig_classes.update_traces(texttemplate=rotulos, textinfo='percent+label', hovertemplate='<b>%{label}</b><br>R$ %{value:,.2f}<br>%{percent}')
    fig_classes.update_layout(uniformtext_mode='hide')
    st.plotly_chart(fig_classes, use_container_width=True)

with col2:
    fig_rf_rv = px.pie(
        df_rf_rv, names='Tipo', values='Valor',
        title='Renda Fixa vs. Renda Variável',
        color_discrete_sequence=['#AB63FA', '#636EFA'], hole=0.45
    )
    fig_rf_rv.update_traces(textinfo='percent+label', hovertemplate='<b>%{label}</b><br>R$ %{value:,.2f}<br>%{percent}')
    st.plotly_chart(fig_rf_rv, use_container_width=True)

with col3:
    df_nac_int = calcular_nacional_vs_internacional(abas)
    fig_nac_int = px.pie(
        df_nac_int, names='Tipo', values='Valor',
        title='Nacional vs. Internacional',
        color_discrete_sequence=['#00CC96', '#19D3F3'], hole=0.45
    )
    fig_nac_int.update_traces(textinfo='percent+label', hovertemplate='<b>%{label}</b><br>R$ %{value:,.2f}<br>%{percent}')
    st.plotly_chart(fig_nac_int, use_container_width=True)

st.divider()

# ── Seção 3: Top 10 Maiores Posições
st.subheader("🏆 Top 10 Maiores Posições")

if not df_top10.empty:
    df_top10['Percentual'] = (df_top10['Valor'] / patrimonio_total * 100).round(2)
    df_top10['Valor Formatado'] = df_top10['Valor'].apply(formatar_moeda)

    fig_top10 = px.bar(
        df_top10, x='Valor', y='Produto', orientation='h',
        color='Classe', color_discrete_map=CORES_CLASSES,
        title='Top 10 Maiores Posições (todas as classes)',
        text=df_top10['Percentual'].apply(lambda x: f"{x:.1f}%"),
        labels={'Valor': 'Valor Atualizado (R$)', 'Produto': ''}
    )
    fig_top10.update_yaxes(ticklabelposition='inside')
    fig_top10.update_traces(textposition='outside')
    fig_top10.update_layout(yaxis={'categoryorder': 'total ascending'})
    st.plotly_chart(fig_top10, use_container_width=True)

st.divider()

# ── Seção 4: Concentração por Classe
st.subheader("🔍 Concentração por Classe")

abas_disponiveis = [aba for aba in COLUNA_VALOR.keys() if aba in abas]
aba_selecionada = st.selectbox("Selecione a classe para detalhar:", abas_disponiveis)

if aba_selecionada:
    col_valor = COLUNA_VALOR[aba_selecionada]
    df_conc = calcular_concentracao_produto(abas[aba_selecionada], col_valor)

    col1, col2 = st.columns(2)

    with col1:
        fig_conc = px.pie(
            df_conc, names='Produto', values=col_valor,
            title=f'Concentração — {aba_selecionada}', hole=0.35
        )
        total = df_conc[col_valor].sum()
        rotulos = ['%{label}<br>%{percent}' if v / total >= 0.05 else '' for v in df_conc[col_valor]]  # ← linha 2
        fig_conc.update_traces(texttemplate=rotulos, textinfo='percent', hovertemplate='<b>%{label}</b><br>R$ %{value:,.2f}<br>%{percent}')
        st.plotly_chart(fig_conc, use_container_width=True)


    with col2:
        df_conc_exib = df_conc.copy()
        df_conc_exib[col_valor] = df_conc_exib[col_valor].apply(formatar_moeda)
        df_conc_exib['Percentual'] = df_conc_exib['Percentual'].apply(lambda x: f"{x:.2f}%")
        df_conc_exib.columns = ['Produto', 'Valor', '% na Classe']
        st.dataframe(df_conc_exib, use_container_width=True, hide_index=True)

st.divider()

# ── Seção 5: Renda Fixa — Indexador e Vencimentos
st.subheader("📅 Análise de Renda Fixa nacional & Tesouro Direto")
col1, col2 = st.columns(2)

with col1:
    df_idx = calcular_distribuicao_indexador(abas)
    if not df_idx.empty:
        fig_idx = px.pie(
            df_idx, names='Indexador', values='Valor',
            title='Distribuição por Indexador', hole=0.4
        )
        fig_idx.update_traces(textinfo='percent+label', hovertemplate='<b>%{label}</b><br>R$ %{value:,.2f}<br>%{percent}')
        st.plotly_chart(fig_idx, use_container_width=True)
    else:
        st.warning("Dados de indexador não encontrados.")

with col2:
    df_venc = calcular_cronograma_vencimentos(abas)
    if not df_venc.empty:
        df_venc['Ano'] = df_venc['Ano'].astype(int).astype(str)
        fig_venc = px.bar(
            df_venc, x='Ano', y='Valor',
            title='Cronograma de Vencimentos por Ano',
            labels={'Ano': 'Ano de Vencimento', 'Valor': 'Valor (R$)'},
            color_discrete_sequence=['#AB63FA'],
            text=df_venc['Valor'].apply(lambda v: formatar_moeda(v)),
            category_orders={'Ano': sorted(df_venc['Ano'].tolist())}
        )
        fig_venc.update_traces(textposition='outside', textfont={'size': 13})
        fig_venc.update_layout(
            xaxis={'type': 'category'},
            uniformtext_minsize=10,
            uniformtext_mode='show'
        )
        st.plotly_chart(fig_venc, use_container_width=True)
    else:
        st.warning("Dados de vencimento não encontrados.")

st.divider()

# ── Seção 6: Investimentos Internacionais
st.subheader("🌎 Investimentos Internacionais")

tem_internacional = any(aba in abas for aba in ABAS_INTERNACIONAIS)

if not tem_internacional:
    st.info("Nenhum dado internacional encontrado no arquivo consolidado.")
else:
    col1, col2, col3 = st.columns(3)

    total_usd = 0.0
    total_brl_ext = 0.0
    for aba_ext in ABAS_INTERNACIONAIS:
        if aba_ext in abas:
            df_ext = abas[aba_ext]
            if 'Valor Atual (USD)' in df_ext.columns:
                total_usd += pd.to_numeric(df_ext['Valor Atual (USD)'], errors='coerce').sum()
            if 'Valor Atual (BRL)' in df_ext.columns:
                total_brl_ext += pd.to_numeric(df_ext['Valor Atual (BRL)'], errors='coerce').sum()

    cotacao_implicita = (total_brl_ext / total_usd) if total_usd > 0 else 0

    with col1:
        st.metric("Total Internacional (USD)", f"US$ {total_usd:,.2f}")
    with col2:
        st.metric("Total Internacional (BRL)", formatar_moeda(total_brl_ext))
    with col3:
        st.metric("Cotação utilizada (USD → BRL)", f"R$ {cotacao_implicita:.4f}")

st.divider()
