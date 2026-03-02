import streamlit as st
import pandas as pd
import os
from github import Github
from io import StringIO
from datetime import datetime

# --- Constants & Config ---
st.set_page_config(page_title="博凯小学五（5）班行为管理系统", layout="wide")

REPO_NAME = "ozr2117-design/BJGL"
STUDENTS_CSV = "students.csv"
HISTORY_CSV = "history.csv"

# 积分规则
DEDUCT_ITEMS = {
    "辱骂/打架": -10,
    "顶嘴": -5,
    "午休喧哗": -5,
    "队伍涣散": -2
}
ADD_ITEMS = {
    "卫生大扫除": 5,
    "机房整理": 5,
    "静音挑战": 5
}

# 状态定义
STATUS_NORMAL = "正常"
STATUS_LOCKED = "物理锁屏"
STATUS_BANNED = "永久封号"

# --- GitHub Integration ---
@st.cache_resource
def get_github_repo():
    if "GITHUB_TOKEN" in st.secrets:
        token = st.secrets["GITHUB_TOKEN"]
    elif "GITHUB_TOKEN" in os.environ:
         token = os.environ["GITHUB_TOKEN"]
    else:
        st.error("无法找到 GITHUB_TOKEN 配置，请确保已在 .streamlit/secrets.toml 中设置！")
        st.stop()
        
    g = Github(token)
    try:
        repo = g.get_repo(REPO_NAME)
        return repo
    except Exception as e:
        st.error(f"连接 GitHub 仓库失败: {e}")
        st.stop()

def get_file_content(repo, filepath):
    """从 GitHub 读取 CSV 文件内容，返回 DataFrame 及 sha"""
    try:
        contents = repo.get_contents(filepath)
        csv_str = contents.decoded_content.decode("utf-8")
        df = pd.read_csv(StringIO(csv_str))
        # 确保关键列存在且类型正确
        if '本周剩余时长' in df.columns:
            df['本周剩余时长'] = pd.to_numeric(df['本周剩余时长'], errors='coerce').fillna(20).astype(int)
        if '严重违规次数' in df.columns:
            df['严重违规次数'] = pd.to_numeric(df['严重违规次数'], errors='coerce').fillna(0).astype(int)
        return df, contents.sha
    except Exception as e:
        return None, None

def update_file_in_github(repo, filepath, df, commit_message, sha=None):
    """将 DataFrame 上传或更新到 GitHub 的 CSV 文件"""
    csv_str = df.to_csv(index=False)
    try:
        if sha:
            repo.update_file(filepath, commit_message, csv_str, sha)
        else:
            repo.create_file(filepath, commit_message, csv_str)
        st.success(f"成功将数据同步至 GitHub: {filepath}!")
    except Exception as e:
        st.error(f"同步至 GitHub 失败: {e}")

# --- Core Logic ---
def init_students_df(names_text):
    """根据文本框输入的名单初始化 DataFrame"""
    names = [name.strip() for name in names_text.split('\n') if name.strip()]
    if not names:
        return None
    data = {
        '姓名': names,
        '本周剩余时长': [20] * len(names),
        '严重违规次数': [0] * len(names),
        '本周状态': [STATUS_NORMAL] * len(names)
    }
    return pd.DataFrame(data)

def evaluate_status(row):
    """根据规则计算当前状态：
    1. 余额 <= 0 -> 物理锁屏
    2. 严重违规 >= 2 -> 永久封号
    如果都不满足，则恢复或保持正常状态 （前提是之前没被永久封号）
    """
    if row['严重违规次数'] >= 2:
        return STATUS_BANNED
    elif row['本周剩余时长'] <= 0:
        return STATUS_LOCKED
    else:
        return STATUS_NORMAL

# --- UI Components ---
def highlight_status(val):
    """为表格中的状态列添加颜色高亮"""
    color = ''
    if val == STATUS_LOCKED:
        color = 'red'
    elif val == STATUS_BANNED:
        color = 'black'
    elif val == STATUS_NORMAL:
        color = 'green'
    return f'color: {color}'

def display_leaderboard(df):
    """展示全班名单排行榜"""
    st.subheader("时 长 排 行 榜")
    sorted_df = df.sort_values(by='本周剩余时长', ascending=False).reset_index(drop=True)
    # 调整列顺序，并应用样式
    styled_df = sorted_df[['姓名', '本周剩余时长', '严重违规次数', '本周状态']].style.map(highlight_status, subset=['本周状态'])
    st.dataframe(styled_df, use_container_width=True, hide_index=True)

# --- Main App Execution ---
def main():
    st.title("🏆 博凯小学五（5）班行为管理系统")
    st.markdown("---")
    
    repo = get_github_repo()
    
    # 尝试加载当前数据
    df, sha = get_file_content(repo, STUDENTS_CSV)
    
    # 初始化流程
    if df is None:
        st.warning(f"由于尚未在云端找到 `{STUDENTS_CSV}` 文件，系统需要初始化。")
        st.subheader("批量导入名单")
        names_input = st.text_area("请输入全班学生名单（一行一个姓名）：", height=300)
        if st.button("初始化名单并同步云端"):
            new_df = init_students_df(names_input)
            if new_df is not None:
                update_file_in_github(repo, STUDENTS_CSV, new_df, "初始化学生名单", sha=None)
                st.rerun() # 重新加载数据
            else:
                st.error("请输入至少一名学生名单！")
        return # 在初始化完成前，不展示其他功能
        
    # --- 侧边栏：操作面板 ---
    with st.sidebar:
        st.header("⚙️ 控制面板")
        st.markdown("---")
        
        st.subheader("📝 积分操作")
        # 多选学生进行操作
        selected_students = st.multiselect("第一步：选择被操作的学生", df['姓名'].tolist())

        
        if selected_students:
            action_type = st.radio("第二步：选择操作类型", ["扣分", "加分"], horizontal=True)
            
            reason = ""
            score_change = 0
            
            if action_type == "扣分":
                reason = st.selectbox("第三步：选择扣分项", list(DEDUCT_ITEMS.keys()))
                score_change = DEDUCT_ITEMS[reason]
            else:
                reason = st.selectbox("第三步：选择加分项", list(ADD_ITEMS.keys()))
                score_change = ADD_ITEMS[reason]
                
            st.info(f"📢 此次操作：**{reason}** ({score_change}分)")
            
            if st.button("确 认 提 交 (同步至云端)", use_container_width=True, type="primary"):
                # 开始修改 DataFrame
                for student in selected_students:
                    idx = df[df['姓名'] == student].index[0]
                    # 修改积分
                    df.loc[idx, '本周剩余时长'] += score_change
                    
                    # 记录严重违规
                    if reason == "辱骂/打架":
                        df.loc[idx, '严重违规次数'] += 1
                        
                # 统一重新评估状态
                df['本周状态'] = df.apply(evaluate_status, axis=1)
                
                # 提交保存
                commit_msg = f"更新数据：操作项 [{reason}]，学生 {', '.join(selected_students)}"
                update_file_in_github(repo, STUDENTS_CSV, df, commit_msg, sha)
                st.rerun()
                
        st.markdown("---")
        st.subheader("🗓️ 周末结算归档")
        st.caption("每周重新开始时，请点击以下按钮归档本周数据并重置基础积分。")
        if st.button("开启新的一周 (危险操作)", use_container_width=True):
            import datetime
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 第一步：备份当前数据到 history.csv
            history_df, hist_sha = get_file_content(repo, HISTORY_CSV)
            current_archive = df.copy()
            current_archive['归档时间'] = now_str
            
            if history_df is not None:
                new_history_df = pd.concat([history_df, current_archive], ignore_index=True)
            else:
                new_history_df = current_archive
                
            update_file_in_github(repo, HISTORY_CSV, new_history_df, f"备份周结算数据 {now_str}", hist_sha)
            
            # 第二步：重置本周数据
            df['本周剩余时长'] = 20
            # 严重违规次数不变，状态重新评估（封号保持封号，其他重置为20的恢复正常）
            df['本周状态'] = df.apply(evaluate_status, axis=1)
            
            update_file_in_github(repo, STUDENTS_CSV, df, f"新的一周开始复位数据 {now_str}", sha)
            st.rerun()

    # --- 主区域：数据概览与排行榜 ---
    # 顶部数据概览
    total_students = len(df)
    locked_count = len(df[df['本周状态'] == STATUS_LOCKED])
    banned_count = len(df[df['本周状态'] == STATUS_BANNED])
    
    metric_cols = st.columns(4)
    metric_cols[0].metric("班级总人数", f"{total_students} 人")
    metric_cols[1].metric("正常游戏人数", f"{total_students - locked_count - banned_count} 人")
    metric_cols[2].metric("本周被锁屏", f"{locked_count} 人", delta_color="inverse")
    metric_cols[3].metric("累计永久封号", f"{banned_count} 人", delta_color="inverse")
    
    st.markdown("---")
    
    # 居中展示排行榜
    display_leaderboard(df)

if __name__ == "__main__":
    main()
