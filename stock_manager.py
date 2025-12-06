import streamlit as st
import pandas as pd
import akshare as ak
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sqlite3
from datetime import datetime, timedelta
import time
import random
import io

# --- 一、整体框架与配置 ---

st.set_page_config(
    page_title="股票数据管理平台",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 使用 session_state 来管理跨页面的状态
if 'db_initialized' not in st.session_state:
    st.session_state.db_initialized = False
if 'stock_data' not in st.session_state:
    st.session_state.stock_data = None
if 'last_updated' not in st.session_state:
    st.session_state.last_updated = {}


# --- 四、数据存储专项 (SQLite) ---

def init_db():
    """初始化数据库，创建股票数据表"""
    if st.session_state.db_initialized:
        return
    conn = sqlite3.connect('stock_data.db')
    cursor = conn.cursor()
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS stock_prices
                   (
                       symbol
                       TEXT,
                       date
                       TEXT,
                       open
                       REAL,
                       high
                       REAL,
                       low
                       REAL,
                       close
                       REAL,
                       volume
                       INTEGER,
                       turnover
                       REAL,
                       amplitude
                       REAL,
                       change_percent
                       REAL,
                       change_amount
                       REAL,
                       turnover_rate
                       REAL,
                       PRIMARY
                       KEY
                   (
                       symbol,
                       date
                   )
                       )
                   ''')
    conn.commit()
    conn.close()
    st.session_state.db_initialized = True
    st.sidebar.success("数据库已初始化！", icon="✅")


def save_to_db(df: pd.DataFrame, symbol: str):
    if df.empty:
        st.warning("没有数据可以保存。")
        return
    conn = sqlite3.connect('stock_data.db')
    df_to_save = df.copy()
    df_to_save.rename(columns={
        '日期': 'date', '代码': 'symbol', '开盘': 'open', '最高': 'high', '最低': 'low', '收盘': 'close',
        '成交量': 'volume', '成交额': 'turnover', '振幅': 'amplitude',
        '涨跌幅': 'change_percent', '涨跌额': 'change_amount', '换手率': 'turnover_rate'
    }, inplace=True)
    df_to_save['date'] = pd.to_datetime(df_to_save['date']).dt.strftime('%Y-%m-%d')
    try:
        df_to_save.to_sql('stock_prices', conn, if_exists='append', index=False)
        st.success(f"成功将 {len(df_to_save)} 条数据存入数据库！")
        st.session_state.last_updated[symbol] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    except sqlite3.IntegrityError as e:
        st.warning(f"部分数据已存在，未重复插入。错误信息: {e}")
    except Exception as e:
        st.error(f"保存到数据库时出错: {e}")
    finally:
        conn.close()


def load_from_db(symbol: str, start_date: str = None, end_date: str = None):
    conn = sqlite3.connect('stock_data.db')
    query = "SELECT * FROM stock_prices WHERE symbol = ?"
    params = [symbol]
    if start_date and end_date:
        query += " AND date BETWEEN ? AND ?"
        params.extend([start_date, end_date])
    query += " ORDER BY date"
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    if not df.empty:
        df.rename(columns={
            'date': '日期', 'symbol': '代码', 'open': '开盘', 'high': '最高', 'low': '最低', 'close': '收盘',
            'volume': '成交量', 'turnover': '成交额', 'amplitude': '振幅',
            'change_percent': '涨跌幅', 'change_amount': '涨跌额', 'turnover_rate': '换手率'
        }, inplace=True)
    return df


def get_all_stocks_in_db():
    conn = sqlite3.connect('stock_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT symbol FROM stock_prices")
    symbols = [row[0] for row in cursor.fetchall()]
    conn.close()
    return symbols


# --- 二、股票数据抓取 (使用akshare) ---

def fetch_stock_data(symbol: str, start_date: str, end_date: str, period: str = "daily"):
    st.info(f"正在从 `akshare` 抓取股票 {symbol} 数据，周期: {period}...")
    try:
        with st.spinner(f"正在抓取 {symbol} ({start_date} 至 {end_date})..."):
            time.sleep(random.uniform(0.5, 1.5))
            stock_df = ak.stock_zh_a_hist(symbol=symbol, period=period, start_date=start_date, end_date=end_date,
                                          adjust="qfq")

            if stock_df.empty:
                st.error(f"未抓取到股票 {symbol} 的数据，请检查代码或日期范围。")
                return None

            stock_df['代码'] = symbol

            st.success(f"成功抓取 {len(stock_df)} 条数据！")
            return stock_df
    except Exception as e:
        st.error(f"抓取数据时发生错误: {e}")
        return None


# --- 三、股票数据显示 (可视化) ---

def display_data_and_charts(df: pd.DataFrame):
    if df is None or df.empty:
        st.warning("请先抓取或加载数据。")
        return

    if '代码' not in df.columns:
        st.error("数据中缺少'代码'列，无法显示。")
        st.write("当前数据列:", df.columns.tolist())
        return

    symbol = df['代码'].iloc[0]
    st.subheader(f"📊 {symbol} 数据概览")
    st.markdown(f"**数据范围**: {df['日期'].min()} 至 {df['日期'].max()}")
    st.subheader("📋 历史数据表格")
    st.data_editor(df, use_container_width=True, num_rows="dynamic", hide_index=True)
    csv = df.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        label="📥 下载CSV数据",
        data=csv,
        file_name=f"{symbol}_stock_data_{datetime.now().strftime('%Y%m%d')}.csv",
        mime='text/csv',
    )
    st.subheader("📈 K线图与技术指标")
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.1,
        row_width=[0.2, 0.7],
        subplot_titles=(f'{symbol} Price', 'Volume')
    )
    fig.add_trace(go.Candlestick(
        x=df['日期'], open=df['开盘'], high=df['最高'], low=df['最低'], close=df['收盘'], name='K线'
    ), row=1, col=1)
    df['MA5'] = df['收盘'].rolling(window=5).mean()
    df['MA10'] = df['收盘'].rolling(window=10).mean()
    df['MA20'] = df['收盘'].rolling(window=20).mean()
    fig.add_trace(go.Scatter(x=df['日期'], y=df['MA5'], line=dict(color='orange', width=1), name='MA5'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df['日期'], y=df['MA10'], line=dict(color='blue', width=1), name='MA10'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df['日期'], y=df['MA20'], line=dict(color='green', width=1), name='MA20'), row=1, col=1)
    fig.add_trace(go.Bar(x=df['日期'], y=df['成交量'], name='Volume', marker_color='lightblue'), row=2, col=1)
    fig.update_layout(
        title=f'{symbol} K线图', yaxis_title='Price', xaxis_rangeslider_visible=False, height=700,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    fig.update_yaxes(title_text="成交量", row=2, col=1)
    st.plotly_chart(fig, use_container_width=True)


# --- 五、核心更新逻辑 ---

def update_single_stock(symbol: str) -> tuple[bool, str, int]:
    """
    更新单只股票，并返回状态。
    返回: (是否成功, 消息, 更新数量)
    """
    try:
        conn = sqlite3.connect('stock_data.db')
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(date) FROM stock_prices WHERE symbol = ?", (symbol,))
        last_date_str = cursor.fetchone()[0]
        conn.close()

        start_date_str = (datetime.strptime(last_date_str, '%Y-%m-%d') + timedelta(days=1)).strftime(
            '%Y%m%d') if last_date_str else (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')
        end_date_str = datetime.now().strftime('%Y%m%d')

        if start_date_str > end_date_str:
            return True, "数据已是最新", 0

        # 静默抓取
        new_df = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=start_date_str, end_date=end_date_str,
                                    adjust="qfq")
        if new_df.empty:
            return True, "无新数据", 0

        new_df['代码'] = symbol
        save_to_db(new_df, symbol)  # 保存到数据库
        return True, f"成功更新 {len(new_df)} 条数据", len(new_df)
    except Exception as e:
        return False, f"更新失败: {e}", 0


def update_stocks_from_list(stock_list: list):
    """批量更新股票列表，并显示进度"""
    if not stock_list:
        st.warning("没有提供需要更新的股票代码。")
        return

    status_container = st.container()
    progress_bar = st.progress(0, text="准备开始...")
    total_stocks = len(stock_list)
    success_count = 0

    results = []

    with status_container:
        for i, symbol in enumerate(stock_list):
            progress_bar.progress((i + 1) / total_stocks, text=f"正在更新 {symbol} ({i + 1}/{total_stocks})...")
            success, message, count = update_single_stock(symbol)
            results.append({"代码": symbol, "状态": "成功" if success else "失败", "信息": message})
            if success:
                success_count += 1

    # --- 最终汇总报告 ---
    progress_bar.empty()
    st.info(f"更新完成！成功: {success_count}/{total_stocks}")
    results_df = pd.DataFrame(results)
    st.dataframe(results_df, use_container_width=True)


# --- Streamlit 主界面 UI ---
st.title("📈 Streamlit 股票数据管理平台")
init_db()
tab1, tab2, tab3 = st.tabs(["🕷️ 数据抓取区", "📊 数据展示区", "🔄 数据管理区"])

with tab1:
    st.header("数据抓取")
    st.markdown("在此区域抓取股票历史数据。我们使用 `akshare` 作为数据源。")

    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        stock_code = st.text_input("输入股票代码", placeholder="例如: 000001", value="000001")
    with col2:
        start_date = st.date_input("选择开始日期", value=datetime.now() - timedelta(days=365))
    with col3:
        end_date = st.date_input("选择结束日期", value=datetime.now())

    period_map = {'日线': 'daily', '周线': 'weekly', '月线': 'monthly'}
    selected_period_cn = st.selectbox("选择 K 线周期", list(period_map.keys()), index=0)
    selected_period_en = period_map[selected_period_cn]

    if st.button("🚀 开始抓取", type="primary"):
        if not stock_code:
            st.error("请输入股票代码！")
        else:
            start_str = start_date.strftime('%Y%m%d')
            end_str = end_date.strftime('%Y%m%d')
            data = fetch_stock_data(stock_code, start_str, end_str, period=selected_period_en)
            if data is not None:
                st.session_state.stock_data = data
                st.success("数据已加载到当前会话，请切换到「数据展示区」查看。")

with tab2:
    st.header("数据展示与可视化")
    display_data = st.session_state.stock_data
    if display_data is None:
        st.info("当前会话无数据，您可以从数据库中选择一只股票进行展示。")
        all_stocks = get_all_stocks_in_db()
        if all_stocks:
            symbol_to_show = st.selectbox("选择要展示的股票", all_stocks, key="db_stock_selector")
            if st.button("加载数据", key="load_from_db_button"):
                display_data = load_from_db(symbol_to_show)
                st.session_state.stock_data = display_data
                st.rerun()
        else:
            st.warning("数据库中暂无数据，请先在「数据抓取区」抓取并保存数据。")
    display_data_and_charts(display_data)

with tab3:
    st.header("数据管理")
    st.subheader("🔄 手动批量更新")

    manual_method = st.radio("选择更新来源", ["🗂️ 上传CSV文件", "📦 从数据库中选择"])

    if manual_method == "🗂️ 上传CSV文件":
        st.write("请上传一个包含'代码'列的CSV文件来批量更新。")
        uploaded_file = st.file_uploader("选择CSV文件", type=["csv"])
        if uploaded_file is not None:
            try:
                df_uploaded = pd.read_csv(uploaded_file)
                if '代码' in df_uploaded.columns:
                    stock_list = df_uploaded['代码'].astype(str).unique().tolist()
                    st.write(f"从文件中识别出 {len(stock_list)} 只股票，准备更新：")
                    st.dataframe(pd.DataFrame(stock_list, columns=['待更新股票代码']))
                    if st.button("▶️ 开始批量更新", type="primary", key="update_from_csv"):
                        update_stocks_from_list(stock_list)
                else:
                    st.error("CSV文件中未找到名为 '代码' 的列！")
            except Exception as e:
                st.error(f"读取CSV文件失败: {e}")
    else:  # 从数据库中选择
        all_stocks_in_db = get_all_stocks_in_db()
        if all_stocks_in_db:
            selected_stocks = st.multiselect("选择要更新的股票", all_stocks_in_db)
            if st.button("▶️ 开始批量更新", type="primary", key="update_from_db"):
                update_stocks_from_list(selected_stocks)
        else:
            st.warning("数据库中暂无数据，请先抓取一些股票。")

# 侧边栏使用说明
st.sidebar.markdown("---")
st.sidebar.markdown("### 📝 使用说明")
st.sidebar.markdown("""
1.  **抓取**: 在「数据抓取区」输入代码、日期和周期，点击抓取。
2.  **查看**: 切换到「数据展示区」查看表格和K线图，并可下载数据。
3.  **更新**: 在「数据管理区」通过上传CSV或选择数据库中的股票来批量更新数据。
""")
