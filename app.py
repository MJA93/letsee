import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from io import BytesIO
import re
from datetime import timedelta

# ── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="محلل جداول المباريات", page_icon="🏟️", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;900&display=swap');
html, body, [class*="css"] { font-family: 'Cairo', sans-serif; direction: rtl; }
[data-testid="stSidebar"] { background: linear-gradient(180deg,#0d1f35 0%,#1a4a72 100%) !important; }
[data-testid="stSidebar"] section { padding: 1rem; }
[data-testid="stSidebar"] label, [data-testid="stSidebar"] p,
[data-testid="stSidebar"] span, [data-testid="stSidebar"] div { color: #e8f4fd !important; }
[data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 { color: white !important; }
[data-testid="stSidebar"] .stButton>button {
    background: linear-gradient(135deg,#f59e0b,#d97706) !important;
    color: white !important; border: none !important; border-radius: 10px !important;
    font-weight: 700 !important; width: 100%; padding: 10px !important;
}
[data-testid="stSidebar"] .stButton>button:hover { opacity: .88; }
[data-testid="stSidebar"] .stSlider [data-testid="stTickBar"] { display:none; }
[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,.2) !important; }
[data-testid="stSidebar"] .stFileUploader { background: rgba(255,255,255,.08); border-radius:10px; padding:10px; }
.kpi-row { display:flex; gap:14px; margin-bottom:20px; flex-wrap:wrap; }
.kpi { background:white; border-radius:14px; padding:16px 20px; flex:1; min-width:140px;
       box-shadow:0 4px 15px rgba(0,0,0,.08); border-top:4px solid var(--c); }
.kpi .val { font-size:2.2rem; font-weight:900; color:var(--c); line-height:1.1; }
.kpi .lbl { font-size:.78rem; color:#888; margin-top:4px; }
div[data-testid="stTabs"] [role="tablist"] button {
    font-size:.95rem; font-weight:600; padding:10px 18px;
}
div[data-testid="stTabs"] [role="tablist"] button[aria-selected="true"] {
    color:#0f2944 !important; border-bottom:3px solid #0f2944 !important;
}
.section-card { background:white; border-radius:16px; padding:22px; box-shadow:0 4px 20px rgba(0,0,0,.07); margin-bottom:18px; }
.heat-wrap { overflow-x:auto; border-radius:12px; }
.heat-wrap table { border-collapse:separate; border-spacing:3px; font-size:13px; }
.heat-wrap th { background:#f1f5f9; padding:7px 10px; border-radius:6px; white-space:nowrap; font-weight:700; color:#374151; }
.heat-wrap td { padding:6px 9px; border-radius:6px; text-align:center; cursor:pointer; font-weight:600; transition:transform .1s; }
.heat-wrap td:hover { transform:scale(1.15); z-index:2; position:relative; }
.badge-group { background:#e0e7ff;color:#3730a3;border-radius:6px;padding:1px 7px;font-size:11px;margin-left:5px; }
.badge-comp  { background:#fef3c7;color:#92400e;border-radius:6px;padding:1px 7px;font-size:11px; }
.move-from   { background:#fee2e2;color:#991b1b;border-radius:8px;padding:2px 10px;font-size:12px;font-weight:700; }
.move-to     { background:#dcfce7;color:#166534;border-radius:8px;padding:2px 10px;font-size:12px;font-weight:700; }
div[data-testid="stExpander"] { border:1px solid #e5e7eb !important; border-radius:12px !important; margin-bottom:8px; }
</style>
""", unsafe_allow_html=True)

# ── Helpers ──────────────────────────────────────────────────────────────────
DAYS_AR = {0:'الاثنين',1:'الثلاثاء',2:'الأربعاء',3:'الخميس',4:'الجمعة',5:'السبت',6:'الأحد'}

def week_start(d):
    return d - timedelta(days=d.weekday())

def heat_bg(v, mx):
    if not v: return "#f8fafc"
    r = v/mx
    if r < .30: return "#bbf7d0"
    if r < .55: return "#fde68a"
    if r < .80: return "#fb923c"
    return "#ef4444"

def heat_fg(v, mx):
    return "white" if mx and v/mx >= .55 else "#1e293b"

def parse_excel(f):
    df = pd.read_excel(f, header=None)
    hrow = 0
    for i, row in df.iterrows():
        if any('التاريخ' in str(c) for c in row): hrow = i; break
    df.columns = df.iloc[hrow]
    df = df.iloc[hrow+1:].reset_index(drop=True)
    df.columns = [str(c).strip() for c in df.columns]

    def fc(df, *kw):
        return next((c for c in df.columns if any(k in c for k in kw)), None)

    date_c  = fc(df,'التاريخ'); time_c  = fc(df,'الوقت')
    match_c = fc(df,'المباراة'); stad_c  = fc(df,'الملعب')
    city_c  = fc(df,'المدينة');  id_c    = fc(df,'رقم')
    comp_c  = fc(df,'المسابقة','الدوري','البطولة')

    if not all([date_c, match_c, city_c]):
        st.error("⚠️ تأكد من وجود أعمدة: التاريخ، المباراة، المدينة"); return None

    rows = []
    for _, row in df.iterrows():
        raw = str(row.get(date_c,''))
        m = re.search(r'(\d{2})-(\d{2})-(\d{4})', raw)
        if not m:
            try: d = pd.Timestamp(row[date_c])
            except: continue
        else:
            d = pd.Timestamp(int(m.group(3)),int(m.group(2)),int(m.group(1)))
        if pd.isnull(d): continue
        ws = week_start(d.date())
        rows.append({
            'id':      str(row.get(id_c,''))   if id_c   else '',
            'dateStr': raw,
            'date':    d.date(),
            'weekday': d.weekday(),
            'dayName': DAYS_AR[d.weekday()],
            'dayFull': d.strftime('%d/%m/%Y'),
            'ws':      ws,
            'wsLabel': ws.strftime('%d/%m'),
            'time':    str(row.get(time_c,'')) if time_c else '',
            'match':   str(row.get(match_c,'')),
            'stadium': str(row.get(stad_c,'')) if stad_c else '',
            'city':    str(row.get(city_c,'')),
            'comp':    str(row.get(comp_c,'')) if comp_c else 'غير محدد',
        })
    df2 = pd.DataFrame(rows).sort_values('date').reset_index(drop=True)
    return df2 if len(df2) else None

def get_eff(city, groups):
    for gname, gcities in groups.items():
        if city in gcities: return gname
    return city

def build_df(df, groups):
    df = df.copy()
    df['eff_city'] = df['city'].apply(lambda c: get_eff(c, groups))
    return df

def compute_redistribution(df, max_per_day):
    """
    Move excess matches per (eff_city, date) to the same weekday in nearest week.
    This keeps each competition on its usual day-of-week.
    """
    moves = []
    # build mutable day counts per city
    day_counts = df.groupby(['eff_city','date']).size().reset_index(name='cnt')

    # index: (eff_city, date) → count
    cnt_map = {(r.eff_city, r.date): r.cnt for _, r in day_counts.iterrows()}

    # all dates per city
    city_dates = df.groupby('eff_city')['date'].apply(sorted).to_dict()

    # iterate each match
    for idx, row in df.iterrows():
        city = row['eff_city']
        d    = row['date']
        wd   = row['weekday']
        if cnt_map.get((city, d), 0) <= max_per_day:
            continue
        # find nearest date with same weekday where city has room
        all_dates = sorted(set(city_dates.get(city, [])))
        same_wd_dates = [x for x in all_dates if x.weekday() == wd and x != d and cnt_map.get((city,x),0) < max_per_day]
        # also allow new weeks (extend ±12 weeks)
        from datetime import date as date_cls
        for delta_w in range(1, 13):
            for sign in [1,-1]:
                cand = d + timedelta(weeks=delta_w*sign)
                if cand.weekday() == wd and cand not in same_wd_dates:
                    same_wd_dates.append(cand)
        if not same_wd_dates:
            continue
        # pick nearest
        target = min(same_wd_dates, key=lambda x: abs((x - d).days))
        if abs((target - d).days) / 7 > 8:  # don't move more than 8 weeks away
            continue
        # do the move
        cnt_map[(city, d)]      = cnt_map.get((city, d), 0) - 1
        cnt_map[(city, target)] = cnt_map.get((city, target), 0) + 1
        moves.append({
            'orig_idx':   idx,
            'city':       city,
            'comp':       row['comp'],
            'match':      row['match'],
            'from_date':  d.strftime('%d/%m/%Y'),
            'from_day':   DAYS_AR[d.weekday()],
            'from_ws':    row['wsLabel'],
            'to_date':    target.strftime('%d/%m/%Y'),
            'to_day':     DAYS_AR[target.weekday()],
            'to_ws':      week_start(target).strftime('%d/%m'),
            'weeks_diff': abs(round((target - d).days / 7)),
        })
    return moves

def to_excel_export(df, moves):
    move_map = {m['orig_idx']: m for m in moves}
    out = df.copy()
    out['أسبوع أصلي']  = out['ws'].apply(lambda x: x.strftime('%d/%m'))
    out['تاريخ مقترح'] = out.index.map(lambda i: move_map[i]['to_date'] if i in move_map else out.loc[i,'dayFull'])
    out['أسبوع مقترح'] = out.index.map(lambda i: move_map[i]['to_ws']   if i in move_map else out.loc[i,'wsLabel'])
    out['تم التحريك']  = out.index.map(lambda i: 'نعم ✓' if i in move_map else '')

    col_map = {'id':'رقم المباراة','dateStr':'التاريخ الأصلي','time':'الوقت','match':'المباراة',
               'stadium':'الملعب','city':'المدينة','eff_city':'المنطقة','comp':'المسابقة'}
    want = ['id','dateStr','time','match','stadium','city','eff_city','comp',
            'أسبوع أصلي','تاريخ مقترح','أسبوع مقترح','تم التحريك']
    out = out[[c for c in want if c in out.columns]].rename(columns=col_map)

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        out.to_excel(writer, sheet_name='الجدول المقترح', index=False)
        if moves:
            mv_df = pd.DataFrame([{
                'المدينة/المنطقة':m['city'],'المسابقة':m['comp'],'المباراة':m['match'],
                'من تاريخ':m['from_date'],'اليوم الأصلي':m['from_day'],
                'إلى تاريخ':m['to_date'],'اليوم المقترح':m['to_day'],
                'فرق الأسابيع':m['weeks_diff'],
            } for m in moves])
            mv_df.to_excel(writer, sheet_name='المباريات المحرّكة', index=False)
    return buf.getvalue()

# ── Session state ────────────────────────────────────────────────────────────
for k,v in [('df_raw',None),('groups',{}),('drill_city',None),('drill_week',None)]:
    if k not in st.session_state: st.session_state[k] = v

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🏟️ محلل جداول المباريات")
    st.markdown("---")
    uploaded = st.file_uploader("📂 رفع ملف Excel", type=['xlsx','xls'])
    if uploaded:
        with st.spinner("⏳ جاري تحليل الملف..."):
            parsed = parse_excel(uploaded)
        if parsed is not None:
            st.session_state.df_raw = parsed
            st.session_state.groups = {}
            st.success(f"✅ {len(parsed)} مباراة محملة")

    if st.session_state.df_raw is not None:
        st.markdown("---")
        max_pd = st.slider("⚙️ الحد الأقصى للمباريات / مدينة / يوم", 1, 30, 8,
                           help="الحد الأقصى لعدد مباريات مدينة واحدة في يوم واحد")

        st.markdown("---")
        st.markdown("### 🏙️ دمج المدن")
        raw_cities = sorted(st.session_state.df_raw['city'].unique())
        taken = [c for g in st.session_state.groups.values() for c in g]
        free  = [c for c in raw_cities if c not in taken]

        with st.expander("➕ إنشاء مجموعة"):
            gname = st.text_input("اسم المنطقة", placeholder="مثال: المنطقة الشرقية", key="gname")
            gcities = st.multiselect("اختر المدن", free, key="gcities")
            if st.button("💾 حفظ المجموعة"):
                if gname and len(gcities) >= 2:
                    st.session_state.groups[gname] = gcities; st.rerun()
                else: st.warning("أدخل اسماً واختر مدينتين على الأقل")

        if st.session_state.groups:
            st.markdown("**المجموعات:**")
            for gn, gc in list(st.session_state.groups.items()):
                c1,c2 = st.columns([4,1])
                c1.markdown(f"**{gn}**: {', '.join(gc)}")
                if c2.button("🗑️", key=f"del_{gn}"):
                    del st.session_state.groups[gn]; st.rerun()

# ── No data state ────────────────────────────────────────────────────────────
if st.session_state.df_raw is None:
    st.markdown("""
    <div style='text-align:center;padding:90px 30px;border:2px dashed #93c5fd;border-radius:20px;
    background:linear-gradient(135deg,#f0f9ff,#e0f2fe);margin-top:20px'>
      <div style='font-size:64px'>🏟️</div>
      <div style='font-size:22px;font-weight:900;color:#0f2944;margin-top:12px'>محلل جداول المباريات</div>
      <div style='font-size:14px;color:#64748b;margin-top:8px'>ارفع ملف Excel من الشريط الجانبي للبدء</div>
      <div style='font-size:12px;color:#94a3b8;margin-top:6px'>يحتاج أعمدة: التاريخ • المباراة • المدينة</div>
    </div>""", unsafe_allow_html=True)
    st.stop()

# ── Build data ───────────────────────────────────────────────────────────────
df        = build_df(st.session_state.df_raw, st.session_state.groups)
eff_cities = sorted(df['eff_city'].unique())
weeks_list = sorted(df['ws'].unique())
moves      = compute_redistribution(df, max_pd)
groups_set = set(st.session_state.groups.keys())

# per-city daily excess
city_excess = {}
for city in eff_cities:
    cdf = df[df['eff_city']==city]
    city_excess[city] = sum(max(0, cnt-max_pd)
        for cnt in cdf.groupby('date').size())

# ── KPI Row ──────────────────────────────────────────────────────────────────
k = [
    (len(df),              "إجمالي المباريات",       "#3b82f6"),
    (len(eff_cities),      "المدن / المناطق",         "#8b5cf6"),
    (len(weeks_list),      "عدد الأسابيع",            "#22c55e"),
    (sum(1 for v in city_excess.values() if v>0), "مناطق فيها تكدس", "#ef4444"),
    (len(moves),           "مباريات تحتاج تحريك",    "#f59e0b"),
]
cols = st.columns(5)
for col,(val,lbl,color) in zip(cols,k):
    col.markdown(f"""
    <div class="kpi" style="--c:{color}">
      <div class="val">{val}</div>
      <div class="lbl">{lbl}</div>
    </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Tabs ─────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["🗺️  خريطة التكدس", "📊  تحليل المدن", "⚖️  إعادة التوزيع"])

# ══ TAB 1 ════════════════════════════════════════════════════════════════════
with tab1:
    # build matrix: eff_city × week
    mat = {}
    for city in eff_cities:
        mat[city] = {}
        for w in weeks_list:
            mat[city][w] = df[(df['eff_city']==city)&(df['ws']==w)]
    max_val = max((len(mat[c][w]) for c in eff_cities for w in weeks_list), default=1)

    # ── Heatmap HTML ─────────────────────────────────────────────────────────
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown("### 🔥 خريطة التكدس الأسبوعي")

    legend_html = """
    <div style='display:flex;gap:10px;margin-bottom:12px;flex-wrap:wrap;align-items:center;'>
      <span style='font-size:13px;color:#555'>التدرج:</span>
      <span style='background:#bbf7d0;padding:3px 12px;border-radius:6px;font-size:12px'>قليل</span>
      <span style='background:#fde68a;padding:3px 12px;border-radius:6px;font-size:12px'>متوسط</span>
      <span style='background:#fb923c;color:white;padding:3px 12px;border-radius:6px;font-size:12px'>كثير</span>
      <span style='background:#ef4444;color:white;padding:3px 12px;border-radius:6px;font-size:12px'>مكتظ ▲</span>
      <span style='font-size:12px;color:#888;margin-right:8px'>▲ = تجاوز الحد اليومي</span>
    </div>"""
    st.markdown(legend_html, unsafe_allow_html=True)

    wk_headers = "".join(f"<th>{w.strftime('%d/%m')}</th>" for w in weeks_list)
    rows_html = ""
    for city in eff_cities:
        badge = f'<span class="badge-group">منطقة</span>' if city in groups_set else ''
        cells = ""
        for w in weeks_list:
            v = len(mat[city][w])
            bg = heat_bg(v, max_val); fg = heat_fg(v, max_val)
            over = "▲" if v > max_pd else ""
            cells += f'<td style="background:{bg};color:{fg}">{(str(v)+over) if v else ""}</td>'
        total = sum(len(mat[city][w]) for w in weeks_list)
        rows_html += f"<tr><td style='text-align:right;background:#f8fafc;white-space:nowrap;padding:6px 12px;font-weight:700'>{badge}{city}</td>{cells}<td style='background:#e2e8f0;font-weight:800;color:#0f2944'>{total}</td></tr>"

    table_html = f"""
    <div class="heat-wrap" dir="rtl">
    <table>
      <thead><tr>
        <th style='text-align:right;min-width:130px'>المدينة / المنطقة</th>
        {wk_headers}
        <th style='background:#e2e8f0'>المجموع</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table></div>"""
    st.markdown(table_html, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # ── Drill-down ────────────────────────────────────────────────────────────
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown("### 📅 تفاصيل الأسبوع")
    dc1, dc2 = st.columns(2)
    sel_city_drill = dc1.selectbox("🏙️ اختر مدينة / منطقة", eff_cities, key="heat_city")
    sel_week_drill = dc2.selectbox("📆 اختر أسبوع", [w.strftime('%d/%m') for w in weeks_list], key="heat_week")

    sel_w_obj = next(w for w in weeks_list if w.strftime('%d/%m')==sel_week_drill)
    drill_matches = mat[sel_city_drill][sel_w_obj]

    if len(drill_matches):
        st.markdown(f"**{len(drill_matches)} مباريات** في {sel_city_drill} — أسبوع {sel_week_drill}")

        # daily bar chart
        day_cnt = drill_matches.groupby('dayName').size().reset_index(name='count')
        day_order = ['الاثنين','الثلاثاء','الأربعاء','الخميس','الجمعة','السبت','الأحد']
        day_cnt['order'] = day_cnt['dayName'].map({d:i for i,d in enumerate(day_order)})
        day_cnt = day_cnt.sort_values('order')
        fig = go.Figure(go.Bar(
            x=day_cnt['dayName'], y=day_cnt['count'],
            marker_color=['#ef4444' if v>max_pd else '#3b82f6' for v in day_cnt['count']],
            text=day_cnt['count'], textposition='outside',
        ))
        fig.add_hline(y=max_pd, line_dash="dash", line_color="#f59e0b",
                      annotation_text=f"الحد: {max_pd}", annotation_position="top right")
        fig.update_layout(height=280, margin=dict(t=20,b=10,l=10,r=10),
                          yaxis_title="عدد المباريات", xaxis_title="",
                          plot_bgcolor='white', paper_bgcolor='white')
        st.plotly_chart(fig, use_container_width=True)

        # detail table per day
        for day in day_order:
            day_ms = drill_matches[drill_matches['dayName']==day]
            if len(day_ms)==0: continue
            over = len(day_ms) > max_pd
            icon = "🔴" if over else "🟢"
            with st.expander(f"{icon} {day} — {len(day_ms)} مباريات {'(يتجاوز الحد)' if over else ''}"):
                for _, r in day_ms.iterrows():
                    comp_badge = f'<span class="badge-comp">{r["comp"]}</span>' if r['comp'] != 'غير محدد' else ''
                    st.markdown(f"⏰ **{r['time']}** — {r['match']} — *{r['stadium']}* {comp_badge}", unsafe_allow_html=True)
    else:
        st.info(f"لا توجد مباريات في {sel_city_drill} خلال أسبوع {sel_week_drill}")
    st.markdown('</div>', unsafe_allow_html=True)

# ══ TAB 2 ════════════════════════════════════════════════════════════════════
with tab2:
    sel_city2 = st.selectbox("🏙️ عرض", ['الكل'] + list(eff_cities), key="city2")
    st.markdown('<div class="section-card">', unsafe_allow_html=True)

    if sel_city2 == 'الكل':
        # weekly total
        wk_totals = [len(df[df['ws']==w]) for w in weeks_list]
        fig = go.Figure(go.Bar(
            x=[w.strftime('%d/%m') for w in weeks_list], y=wk_totals,
            marker_color=['#ef4444' if v > max_pd*len(eff_cities)*.5 else '#3b82f6' for v in wk_totals],
            text=wk_totals, textposition='outside',
        ))
        fig.update_layout(title="إجمالي المباريات أسبوعياً", height=320,
                          margin=dict(t=40,b=10,l=10,r=10),
                          plot_bgcolor='white', paper_bgcolor='white')
        st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

        # summary table
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown("### 📋 ملخص التكدس لكل مدينة / منطقة")
        summary = []
        for city in eff_cities:
            cdf = df[df['eff_city']==city]
            day_counts = cdf.groupby('date').size()
            total=len(cdf); active=cdf['ws'].nunique()
            max_day = day_counts.max() if len(day_counts) else 0
            over_days = (day_counts > max_pd).sum()
            excess = day_counts.apply(lambda x: max(0,x-max_pd)).sum()
            summary.append({'المدينة/المنطقة':city,'المجموع':total,'أسابيع نشطة':active,
                            'أعلى يوم':int(max_day),'أيام تتجاوز الحد':int(over_days),
                            'مباريات تحتاج تحريك':int(excess)})
        s_df = pd.DataFrame(summary).sort_values('مباريات تحتاج تحريك',ascending=False)
        st.dataframe(s_df.style.background_gradient(subset=['مباريات تحتاج تحريك'],cmap='Reds'),
                     use_container_width=True, hide_index=True)
    else:
        cdf = df[df['eff_city']==sel_city2]
        cur   = [len(cdf[cdf['ws']==w]) for w in weeks_list]
        after = list(cur)
        for mv in moves:
            if mv['city']==sel_city2:
                fi = next((i for i,w in enumerate(weeks_list) if w.strftime('%d/%m')==mv['from_ws']),None)
                ti = next((i for i,w in enumerate(weeks_list) if w.strftime('%d/%m')==mv['to_ws']),None)
                if fi is not None and ti is not None:
                    after[fi]=max(0,after[fi]-1); after[ti]+=1
        labels = [w.strftime('%d/%m') for w in weeks_list]
        fig = go.Figure()
        fig.add_trace(go.Bar(name='حالي', x=labels, y=cur, marker_color='#ef4444', opacity=.85))
        fig.add_trace(go.Bar(name='مقترح', x=labels, y=after, marker_color='#22c55e', opacity=.85))
        fig.add_hline(y=max_pd, line_dash="dash", line_color="#f59e0b",
                      annotation_text=f"الحد: {max_pd}", annotation_position="top right")
        fig.update_layout(barmode='group', title=f"مباريات {sel_city2} — حالي مقابل مقترح",
                          height=340, margin=dict(t=40,b=10,l=10,r=10),
                          plot_bgcolor='white', paper_bgcolor='white', legend=dict(x=0,y=1.1,orientation='h'))
        st.plotly_chart(fig, use_container_width=True)

        # competition breakdown
        comp_counts = cdf.groupby('comp').size().reset_index(name='count').sort_values('count',ascending=False)
        if len(comp_counts) > 1:
            fig2 = px.pie(comp_counts, names='comp', values='count', title="توزيع المسابقات",
                          color_discrete_sequence=px.colors.qualitative.Set2)
            fig2.update_layout(height=280, margin=dict(t=40,b=0,l=0,r=0))
            st.plotly_chart(fig2, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ══ TAB 3 ════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    col_h, col_btn = st.columns([3,2])
    col_h.markdown(f"### ⚖️ المباريات المقترح إعادة جدولتها &nbsp; `{len(moves)}`")

    if moves:
        excel_bytes = to_excel_export(df, moves)
        col_btn.download_button("📥 تحميل الجدول المقترح (.xlsx)", data=excel_bytes,
                                file_name="الجدول_المقترح.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    if not moves:
        st.success(f"✅ جميع المدن ضمن الحد المحدد ({max_pd} مباريات/يوم) — لا يوجد تكدس يستدعي التدخل")
    else:
        # summary chart per city
        city_move_cnt = pd.Series([m['city'] for m in moves]).value_counts().reset_index()
        city_move_cnt.columns = ['مدينة','عدد المباريات']
        fig = px.bar(city_move_cnt, x='مدينة', y='عدد المباريات',
                     color='عدد المباريات', color_continuous_scale='Reds',
                     title="عدد المباريات المقترح تحريكها لكل مدينة")
        fig.update_layout(height=280, margin=dict(t=40,b=10,l=10,r=10),
                          plot_bgcolor='white', paper_bgcolor='white', coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

        # filter
        f1, f2 = st.columns(2)
        city_f = f1.selectbox("تصفية بالمدينة", ['الكل']+list({m['city'] for m in moves}), key="mv_city")
        comp_f = f2.selectbox("تصفية بالمسابقة", ['الكل']+list({m['comp'] for m in moves}), key="mv_comp")

        disp = [m for m in moves
                if (city_f=='الكل' or m['city']==city_f)
                and (comp_f=='الكل' or m['comp']==comp_f)]

        rows_html = ""
        for m in disp:
            badge_c = f'<span class="badge-group">{m["city"]}</span>'
            badge_comp = f'<span class="badge-comp">{m["comp"]}</span>'
            rows_html += f"""
            <tr style='border-bottom:1px solid #f0f0f0'>
              <td style='padding:9px 12px'>{badge_c}</td>
              <td style='padding:9px 12px'>{badge_comp}</td>
              <td style='padding:9px 12px;font-weight:600'>{m['match']}</td>
              <td style='padding:9px 12px;text-align:center'>
                <span class='move-from'>{m['from_day']} {m['from_date']}</span></td>
              <td style='padding:9px 12px;text-align:center'>
                <span class='move-to'>{m['to_day']} {m['to_date']}</span></td>
              <td style='padding:9px 12px;text-align:center;color:{"#ef4444" if m["weeks_diff"]>3 else "#555"};font-weight:{"700" if m["weeks_diff"]>3 else "400"}'>
                {m["weeks_diff"]} {"أسبوع" if m["weeks_diff"]==1 else "أسابيع"}</td>
            </tr>"""

        tbl = f"""
        <div style='overflow-x:auto;direction:rtl'>
        <table style='width:100%;border-collapse:collapse;font-size:13px;font-family:Cairo,sans-serif'>
          <thead><tr style='background:#f8fafc;'>
            <th style='padding:10px 12px;text-align:right;border-bottom:2px solid #e5e7eb'>المدينة</th>
            <th style='padding:10px 12px;text-align:right;border-bottom:2px solid #e5e7eb'>المسابقة</th>
            <th style='padding:10px 12px;text-align:right;border-bottom:2px solid #e5e7eb'>المباراة</th>
            <th style='padding:10px 12px;text-align:center;border-bottom:2px solid #e5e7eb'>من تاريخ</th>
            <th style='padding:10px 12px;text-align:center;border-bottom:2px solid #e5e7eb'>إلى تاريخ</th>
            <th style='padding:10px 12px;text-align:center;border-bottom:2px solid #e5e7eb'>فرق الأسابيع</th>
          </tr></thead>
          <tbody>{rows_html}</tbody>
        </table></div>"""
        st.markdown(tbl, unsafe_allow_html=True)
        st.caption(f"يعرض {len(disp)} من {len(moves)} مباراة")
    st.markdown('</div>', unsafe_allow_html=True)
