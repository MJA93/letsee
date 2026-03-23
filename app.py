import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import re
from datetime import timedelta

# ─── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="محلل جداول المباريات",
    page_icon="🏟️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  body, .stApp { direction: rtl; font-family: 'Segoe UI', Tahoma, sans-serif; }
  h1,h2,h3,h4 { text-align: right; }
  .block-container { padding-top: 1.5rem; }
  div[data-testid="stMetricValue"] { font-size: 2rem; }
  .heat-table td, .heat-table th { text-align: center; padding: 6px 10px; border-radius: 5px; }
</style>
""", unsafe_allow_html=True)

# ─── Helpers ───────────────────────────────────────────────────────────────────
DAYS_AR = {0:'الاثنين',1:'الثلاثاء',2:'الأربعاء',3:'الخميس',4:'الجمعة',5:'السبت',6:'الأحد'}

def week_start(d):
    return d - timedelta(days=d.weekday())

def heat_color(val, max_val):
    if val == 0 or max_val == 0:
        return "#f1f5f9"
    r = val / max_val
    if r < 0.35: return "#bbf7d0"
    if r < 0.60: return "#fde68a"
    if r < 0.85: return "#fb923c"
    return "#ef4444"

def text_color(val, max_val):
    if max_val == 0: return "#1e293b"
    return "white" if val/max_val >= 0.60 else "#1e293b"

def parse_excel(uploaded):
    df = pd.read_excel(uploaded, header=None)
    # find header row
    hrow = 0
    for i, row in df.iterrows():
        if any('التاريخ' in str(c) for c in row):
            hrow = i; break
    df.columns = df.iloc[hrow]
    df = df.iloc[hrow+1:].reset_index(drop=True)
    df.columns = [str(c).strip() for c in df.columns]

    date_col   = next((c for c in df.columns if 'التاريخ' in c), None)
    time_col   = next((c for c in df.columns if 'الوقت'   in c), None)
    match_col  = next((c for c in df.columns if 'المباراة' in c), None)
    stad_col   = next((c for c in df.columns if 'الملعب'  in c), None)
    city_col   = next((c for c in df.columns if 'المدينة' in c), None)
    id_col     = next((c for c in df.columns if 'رقم'     in c), None)

    if not all([date_col, match_col, city_col]):
        st.error("⚠️ تأكد أن الملف يحتوي على أعمدة: التاريخ، المباراة، المدينة")
        return None

    rows = []
    for _, row in df.iterrows():
        raw = str(row.get(date_col, ''))
        m = re.search(r'(\d{2})-(\d{2})-(\d{4})', raw)
        if not m:
            try:
                d = pd.to_datetime(row[date_col])
            except:
                continue
        else:
            d = pd.Timestamp(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        if pd.isnull(d): continue
        ws = week_start(d.date())
        rows.append({
            'id':       str(row.get(id_col,''))   if id_col   else '',
            'dateStr':  raw,
            'date':     d.date(),
            'ws':       ws,
            'wsLabel':  ws.strftime('%d/%m'),
            'dayName':  DAYS_AR[d.weekday()],
            'dayFull':  d.strftime('%d/%m/%Y'),
            'time':     str(row.get(time_col,'')) if time_col else '',
            'match':    str(row.get(match_col,'')),
            'stadium':  str(row.get(stad_col,'')) if stad_col else '',
            'city':     str(row.get(city_col,'')),
        })
    return pd.DataFrame(rows).sort_values('date').reset_index(drop=True)

def get_eff_city(city, groups):
    for gname, gcities in groups.items():
        if city in gcities:
            return gname
    return city

def build_matrix(df, groups):
    df = df.copy()
    df['eff_city'] = df['city'].apply(lambda c: get_eff_city(c, groups))
    return df

def compute_redistribution(df, max_per_week):
    moves = []
    eff_cities = df['eff_city'].unique()
    weeks_sorted = sorted(df['ws'].unique())

    for city in eff_cities:
        cdf = df[df['eff_city']==city].copy()
        wk = {w: list(cdf[cdf['ws']==w].index) for w in weeks_sorted}
        counts = {w: len(v) for w,v in wk.items()}
        week_list = weeks_sorted

        for i, wi in enumerate(week_list):
            while counts[wi] > max_per_week:
                best_j, best_d = -1, 9999
                for j, wj in enumerate(week_list):
                    if j==i: continue
                    if counts[wj] < max_per_week:
                        d = abs(j-i)
                        if d < best_d: best_d=d; best_j=j
                if best_j == -1: break
                wj = week_list[best_j]
                idx = wk[wi].pop()
                wk[wj].append(idx)
                counts[wi] -= 1
                counts[wj] += 1
                row = df.loc[idx]
                moves.append({
                    'city': city,
                    'match': row['match'],
                    'from_ws': wi.strftime('%d/%m'),
                    'to_ws':   wj.strftime('%d/%m'),
                    'weeks_diff': abs(best_j-i),
                    'orig_idx': idx,
                    'new_ws': wj,
                })
    return moves

def to_excel(df, moves):
    move_map = {m['orig_idx']: m['to_ws'].strftime('%d/%m') for m in moves}
    out = df.copy()
    out['أسبوع أصلي']   = out['ws'].apply(lambda x: x.strftime('%d/%m'))
    out['أسبوع مقترح']  = out.index.map(lambda i: move_map.get(i, out.loc[i,'ws'].strftime('%d/%m')))
    out['تم التحريك']   = out.index.map(lambda i: 'نعم ✓' if i in move_map else '')

    rename = {'id':'رقم المباراة','dateStr':'التاريخ الأصلي','time':'الوقت',
              'match':'المباراة','stadium':'الملعب','city':'المدينة','eff_city':'المنطقة'}
    cols = ['id','dateStr','time','match','stadium','city','eff_city','أسبوع أصلي','أسبوع مقترح','تم التحريك']
    out = out[[c for c in cols if c in out.columns]].rename(columns=rename)

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        out.to_excel(writer, sheet_name='الجدول المقترح', index=False)
        if moves:
            mv_df = pd.DataFrame([{
                'المدينة/المنطقة': m['city'],
                'المباراة':        m['match'],
                'من أسبوع':        m['from_ws'],
                'إلى أسبوع':       m['to_ws'],
                'فرق الأسابيع':    m['weeks_diff'],
            } for m in moves])
            mv_df.to_excel(writer, sheet_name='المباريات المحرّكة', index=False)
    return buf.getvalue()

# ─── Session state ─────────────────────────────────────────────────────────────
if 'df_raw'  not in st.session_state: st.session_state.df_raw  = None
if 'groups'  not in st.session_state: st.session_state.groups  = {}   # {name: [cities]}

# ─── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🏟️ محلل جداول المباريات")
    st.markdown("---")

    uploaded = st.file_uploader("📂 رفع ملف Excel", type=['xlsx','xls'])
    if uploaded:
        with st.spinner("⏳ جاري تحليل الملف..."):
            df_parsed = parse_excel(uploaded)
        if df_parsed is not None:
            st.session_state.df_raw = df_parsed
            st.success(f"✅ {len(df_parsed)} مباراة")

    if st.session_state.df_raw is not None:
        st.markdown("---")
        max_pw = st.slider("⚙️ الحد الأقصى للمباريات في المدينة أسبوعياً", 1, 40, 8)

        st.markdown("---")
        st.markdown("### 🏙️ دمج المدن")
        raw_cities = sorted(st.session_state.df_raw['city'].unique())
        already_grouped = [c for g in st.session_state.groups.values() for c in g]

        with st.expander("➕ إنشاء / تعديل مجموعة"):
            grp_name = st.text_input("اسم المنطقة", placeholder="مثال: المنطقة الشرقية")
            free_cities = [c for c in raw_cities if c not in already_grouped]
            sel_cities  = st.multiselect("اختر المدن", free_cities)
            if st.button("💾 حفظ المجموعة"):
                if grp_name and len(sel_cities) >= 2:
                    st.session_state.groups[grp_name] = sel_cities
                    st.rerun()
                else:
                    st.warning("أدخل اسماً واختر مدينتين على الأقل")

        if st.session_state.groups:
            st.markdown("**المجموعات المحفوظة:**")
            for gname, gcities in list(st.session_state.groups.items()):
                c1, c2 = st.columns([4,1])
                c1.markdown(f"**{gname}**: {', '.join(gcities)}")
                if c2.button("🗑️", key=f"del_{gname}"):
                    del st.session_state.groups[gname]
                    st.rerun()

# ─── Main ──────────────────────────────────────────────────────────────────────
if st.session_state.df_raw is None:
    st.markdown("""
    <div style='text-align:center;padding:80px 20px;border:2.5px dashed #93c5fd;border-radius:14px;background:white;margin-top:30px'>
      <div style='font-size:60px'>📊</div>
      <div style='font-size:20px;font-weight:600;color:#1e3a5f;margin-top:10px'>ارفع ملف Excel من الشريط الجانبي للبدء</div>
      <div style='font-size:13px;color:#aaa;margin-top:6px'>يحتاج أعمدة: التاريخ، المباراة، المدينة</div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

df = build_matrix(st.session_state.df_raw, st.session_state.groups)
eff_cities  = sorted(df['eff_city'].unique())
weeks_list  = sorted(df['ws'].unique())
week_labels = {w: w.strftime('%d/%m') for w in weeks_list}
moves       = compute_redistribution(df, max_pw)

# KPIs
k1,k2,k3,k4,k5 = st.columns(5)
city_excess = {}
for city in eff_cities:
    cdf = df[df['eff_city']==city]
    ex = sum(max(0, len(cdf[cdf['ws']==w])-max_pw) for w in weeks_list)
    city_excess[city] = ex

k1.metric("إجمالي المباريات",   len(df))
k2.metric("المدن / المناطق",   len(eff_cities))
k3.metric("عدد الأسابيع",      len(weeks_list))
k4.metric("مناطق فيها تكدس",  sum(1 for v in city_excess.values() if v>0))
k5.metric("مباريات تحتاج تحريك", len(moves))

st.markdown("---")
tab1, tab2, tab3 = st.tabs(["🗺️ خريطة التكدس", "📊 تحليل المدن", "⚖️ إعادة التوزيع"])

# ── TAB 1: Heatmap ─────────────────────────────────────────────────────────────
with tab1:
    st.markdown("### خريطة التكدس الأسبوعية")
    st.caption("💡 الأرقام تمثل عدد المباريات — اللون الأحمر يعني تجاوز الحد المحدد")

    # build matrix
    mat = {}
    for city in eff_cities:
        mat[city] = {}
        for w in weeks_list:
            mat[city][w] = len(df[(df['eff_city']==city) & (df['ws']==w)])

    max_val = max((mat[c][w] for c in eff_cities for w in weeks_list), default=1)

    # legend
    lc1,lc2,lc3,lc4,_ = st.columns([1,1,1,1,4])
    lc1.markdown('<span style="background:#bbf7d0;padding:3px 10px;border-radius:5px">قليل</span>', unsafe_allow_html=True)
    lc2.markdown('<span style="background:#fde68a;padding:3px 10px;border-radius:5px">متوسط</span>', unsafe_allow_html=True)
    lc3.markdown('<span style="background:#fb923c;color:white;padding:3px 10px;border-radius:5px">كثير</span>', unsafe_allow_html=True)
    lc4.markdown('<span style="background:#ef4444;color:white;padding:3px 10px;border-radius:5px">مكتظ ▲</span>', unsafe_allow_html=True)

    # render HTML table
    headers = "".join(f"<th style='padding:6px 10px;background:#f1f5f9;min-width:44px'>{week_labels[w]}</th>" for w in weeks_list)
    total_col = "<th style='padding:6px 10px;background:#e2e8f0;font-weight:700'>المجموع</th>"
    is_group = set(st.session_state.groups.keys())

    rows_html = ""
    for city in eff_cities:
        total = sum(mat[city].values())
        badge = "<span style='background:#e0e7ff;color:#3730a3;border-radius:5px;padding:1px 5px;font-size:11px;margin-left:4px'>منطقة</span>" if city in is_group else ""
        cells = ""
        for w in weeks_list:
            v = mat[city][w]
            bg = heat_color(v, max_val)
            tc = text_color(v, max_val)
            over = "▲" if v > max_pw else ""
            cells += f"<td style='background:{bg};color:{tc};text-align:center;padding:5px 8px;border-radius:4px;font-weight:{'700' if v>max_pw else '400'}'>{v if v else ''}{over}</td>"
        rows_html += f"<tr><td style='padding:5px 10px;font-weight:600;background:#fafafa;white-space:nowrap'>{badge}{city}</td>{cells}<td style='text-align:center;font-weight:700;background:#f1f5f9;padding:5px 8px'>{total}</td></tr>"

    html_table = f"""
    <div style='overflow-x:auto;direction:rtl'>
    <table style='border-collapse:separate;border-spacing:3px;font-size:13px;width:100%'>
      <thead><tr>
        <th style='padding:6px 10px;background:#f1f5f9;text-align:right;min-width:120px'>المدينة / المنطقة</th>
        {headers}{total_col}
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table></div>"""
    st.markdown(html_table, unsafe_allow_html=True)

    # daily drill
    st.markdown("---")
    st.markdown("#### 📅 التوزيع اليومي التفصيلي")
    sel_drill = st.selectbox("اختر مدينة / منطقة", eff_cities, key="drill")
    drill_df = df[df['eff_city']==sel_drill].copy()
    drill_df['day_label'] = drill_df['dayName'] + ' ' + drill_df['dayFull']
    day_counts = drill_df.groupby('day_label').size().reset_index(name='count')
    st.bar_chart(day_counts.set_index('day_label')['count'])

    for day, grp in drill_df.groupby('day_label', sort=False):
        with st.expander(f"📆 {day} — {len(grp)} مباريات"):
            for _, r in grp.iterrows():
                st.markdown(f"⏰ **{r['time']}** — {r['match']} — *{r['stadium']}*")

# ── TAB 2: City Analysis ───────────────────────────────────────────────────────
with tab2:
    st.markdown("### تحليل المدن والمناطق")
    sel_city = st.selectbox("اختر مدينة أو عرض الكل", ['الكل'] + list(eff_cities), key="city_sel")

    if sel_city == 'الكل':
        chart_data = pd.DataFrame({
            'الأسبوع':   [week_labels[w] for w in weeks_list],
            'عدد المباريات': [len(df[df['ws']==w]) for w in weeks_list],
        }).set_index('الأسبوع')
        st.bar_chart(chart_data)

        summary = []
        for city in eff_cities:
            cdf = df[df['eff_city']==city]
            wc = [len(cdf[cdf['ws']==w]) for w in weeks_list]
            total = sum(wc); active = sum(1 for x in wc if x>0)
            max_  = max(wc) if wc else 0
            over  = sum(1 for x in wc if x>max_pw)
            excess= sum(max(0,x-max_pw) for x in wc)
            summary.append({'المدينة/المنطقة':city,'المجموع':total,'أسابيع نشطة':active,
                            'أعلى أسبوع':max_,'أسابيع متجاوزة':over,'تحتاج تحريك':excess})
        s_df = pd.DataFrame(summary).sort_values('تحتاج تحريك', ascending=False)
        st.dataframe(s_df, use_container_width=True, hide_index=True)
    else:
        cdf = df[df['eff_city']==sel_city]
        cur   = [len(cdf[cdf['ws']==w]) for w in weeks_list]
        after = cur.copy()
        for mv in moves:
            if mv['city']==sel_city:
                fi = next((i for i,w in enumerate(weeks_list) if w.strftime('%d/%m')==mv['from_ws']), None)
                ti = next((i for i,w in enumerate(weeks_list) if w.strftime('%d/%m')==mv['to_ws']),   None)
                if fi is not None and ti is not None:
                    after[fi] = max(0, after[fi]-1); after[ti] += 1
        chart_df = pd.DataFrame({'حالي':cur,'مقترح':after}, index=[week_labels[w] for w in weeks_list])
        st.bar_chart(chart_df)

# ── TAB 3: Redistribution ──────────────────────────────────────────────────────
with tab3:
    st.markdown(f"### ⚖️ مباريات مقترح إعادة جدولتها &nbsp; `{len(moves)}`")

    if not moves:
        st.success(f"✅ جميع المدن ضمن الحد المحدد ({max_pw} مباريات/أسبوع)")
    else:
        city_filter = st.selectbox("تصفية حسب المدينة", ['الكل'] + list({m['city'] for m in moves}), key="mv_city")
        disp_moves = moves if city_filter=='الكل' else [m for m in moves if m['city']==city_filter]

        mv_df = pd.DataFrame([{
            'المدينة/المنطقة': m['city'],
            'المباراة':        m['match'],
            'من أسبوع':        m['from_ws'],
            'إلى أسبوع':       m['to_ws'],
            'فرق الأسابيع':    m['weeks_diff'],
        } for m in disp_moves])
        st.dataframe(mv_df, use_container_width=True, hide_index=True)

        st.markdown("---")
        excel_bytes = to_excel(df, moves)
        st.download_button(
            label="📥 تحميل الجدول المقترح (.xlsx)",
            data=excel_bytes,
            file_name="الجدول_المقترح.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
