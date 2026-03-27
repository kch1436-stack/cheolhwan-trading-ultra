
import math
from datetime import date
import pandas as pd
import streamlit as st

st.set_page_config(page_title="철환 트레이딩 시스템 ULTRA", page_icon="🚀", layout="wide")

if "journal" not in st.session_state:
    st.session_state.journal = pd.DataFrame(columns=[
        "날짜","종목","시간봉","방향","자리등급","체크점수","결과(%)","실수유형","원칙준수","메모"
    ])
for k, v in {
    "daily_loss_limit_pct": 6.0,
    "daily_loss_used_pct": 0.0,
    "daily_trade_limit": 2,
    "daily_trades_used": 0,
    "day_mode": True,
    "last_grade": "미판정",
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

def calc_trade(balance, risk_pct, direction, entry, stop, tp1, tp2, max_lev, fee_pct):
    if min(balance, risk_pct, entry, stop, tp1) <= 0:
        return {"status": "입력값 오류"}
    if entry == stop:
        return {"status": "진입가와 손절가 동일"}
    risk_amount = balance * (risk_pct / 100.0)
    stop_distance = abs(entry - stop)
    stop_pct = (stop_distance / entry) * 100.0
    position_notional = risk_amount / (stop_distance / entry)
    qty = position_notional / entry
    required_lev = position_notional / balance
    if direction == "Long":
        rr1 = (tp1 - entry) / (entry - stop) if (entry - stop) != 0 else 0.0
        rr2 = (tp2 - entry) / (entry - stop) if (entry - stop) != 0 else 0.0
        stop_valid = stop < entry
        tp1_valid = tp1 > entry
        tp2_valid = tp2 > entry
    else:
        rr1 = (entry - tp1) / (stop - entry) if (stop - entry) != 0 else 0.0
        rr2 = (entry - tp2) / (stop - entry) if (stop - entry) != 0 else 0.0
        stop_valid = stop > entry
        tp1_valid = tp1 < entry
        tp2_valid = tp2 < entry
    issues = []
    if not stop_valid:
        issues.append("손절 방향 오류")
    if not tp1_valid:
        issues.append("TP1 방향 오류")
    if not tp2_valid:
        issues.append("TP2 방향 오류")
    if required_lev > max_lev:
        issues.append("최대 레버리지 초과")
    if rr1 < 1.5:
        issues.append("손익비 낮음")
    if stop_pct < 0.15:
        issues.append("손절폭 너무 짧음")
    return {
        "status": "OK" if not issues else " / ".join(issues),
        "risk_amount": risk_amount,
        "stop_pct": stop_pct,
        "position_notional": position_notional,
        "qty": qty,
        "required_lev": required_lev,
        "recommended_lev": max(1, math.ceil(required_lev)),
        "rr1": rr1,
        "rr2": rr2,
    }

def grade_logic(score):
    if score >= 7:
        return "A급", "진입 검토 가능"
    if score >= 5:
        return "B급", "소액 또는 대기"
    return "쓰레기", "진입 금지"

def ultra_decision(score, structure, hl_lh, stop_clarity, rr, eth_align, candle_closed):
    reasons = []
    if not structure:
        reasons.append("구조 깨짐 미확인")
    if not hl_lh:
        reasons.append("HL/LH 미확인")
    if not stop_clarity:
        reasons.append("손절 기준 불명확")
    if not rr:
        reasons.append("손익비 1:2 미만 가능성")
    if not eth_align:
        reasons.append("ETH 방향 확인 부족")
    if not candle_closed:
        reasons.append("봉 마감 확인 부족")
    if score >= 8 and not reasons:
        return "진입 허가", "A급", reasons
    if score >= 5:
        return "관찰만", "B급", reasons
    return "진입 금지", "쓰레기", reasons

def scenario_text(symbol, direction, structure, hl_lh, rebreak, prz):
    if direction == "Long":
        now = "현재는 구조와 HL이 확인되기 전까지 대기."
        long_s = "롱 확정: 구조 깨짐 → 눌림 → HL → 고점 재돌파."
        short_s = "반대: 반등 실패 후 저점 재이탈 시 하락 continuation."
    else:
        now = "현재는 구조와 LH가 확인되기 전까지 대기."
        long_s = "반대: 구조 재전환 후 HL 형성 시 숏 무효 가능성."
        short_s = "숏 확정: 구조 깨짐 → 반등 → LH → 저점 재이탈."
    if not structure:
        now += " 구조가 핵심."
    if prz:
        now += " PRZ 반응은 보조 근거."
    if not hl_lh:
        now += " HL/LH 없으면 진입보다 관찰."
    if not rebreak:
        now += " 재돌파/재이탈 확인 전 추격 금지."
    return f"{symbol} 시나리오\n- {now}\n- {long_s}\n- {short_s}"

def make_x_post(symbol, timeframe, direction, grade, entry, stop, tp1, tp2, notes):
    arrow = "📉➡️📈" if direction == "Long" else "📈➡️📉"
    side = "롱" if direction == "Long" else "숏"
    return f'''{symbol} {timeframe} 📊

{side} 시나리오 {arrow}
자리 등급: {grade}

📍진입: {entry:,.2f}
🛑손절: {stop:,.2f}
🎯TP1: {tp1:,.2f}
🎯TP2: {tp2:,.2f}

메모:
{notes}

추격 금지 ❌
자리만 간다 🎯

#{symbol.replace("/", "").replace("-", "")} #트레이딩'''

def recent_warnings(df):
    out = []
    if df.empty:
        return out
    recent = df.tail(10).copy()
    counts = recent["실수유형"].value_counts()
    for key in ["추격 진입","HL 전 선진입","RSI만 보고 진입","손절 늦음","손절 기준 불명확"]:
        if counts.get(key, 0) >= 2:
            out.append(f"최근 10회 중 '{key}'이 {counts.get(key)}번 발생.")
    recent["결과(%)"] = pd.to_numeric(recent["결과(%)"], errors="coerce").fillna(0)
    trash = recent[recent["자리등급"] == "쓰레기"]
    if not trash.empty and trash["결과(%)"].mean() < 0:
        out.append("쓰레기 자리 평균 결과가 음수다. 진입 자체를 줄여라.")
    a_df = recent[recent["자리등급"] == "A급"]
    if not a_df.empty and a_df["결과(%)"].mean() > 0:
        out.append("A급 자리만 집중했을 때 성과가 더 좋다.")
    return out

st.title("🚀 철환 트레이딩 시스템 ULTRA")
st.caption("이미지 업로드 + 자동 인터뷰 + 진입 허가/금지 엔진 + 양방향 시나리오 + 실수 재발 경고")

tabs = st.tabs([
    "실전 대시보드","ULTRA 이미지 엔진","진입 판정기","포지션 계산기",
    "복리 추적기","매매일지","통계","X 게시물"
])

with tabs[0]:
    st.subheader("실전 대시보드")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("오늘 손실 한도", f"{st.session_state.daily_loss_limit_pct:.1f}%")
    c2.metric("오늘 사용 손실", f"{st.session_state.daily_loss_used_pct:.1f}%")
    c3.metric("남은 트레이드 수", f"{max(0, st.session_state.daily_trade_limit - st.session_state.daily_trades_used)}")
    c4.metric("최근 판정", st.session_state.last_grade)
    left, right = st.columns(2)
    with left:
        st.session_state.day_mode = st.checkbox("4월 1일 실전 모드 사용", value=st.session_state.day_mode)
        st.session_state.daily_loss_limit_pct = st.number_input("하루 손실 제한 (%)", min_value=1.0, max_value=20.0, value=float(st.session_state.daily_loss_limit_pct), step=0.5)
        st.session_state.daily_trade_limit = st.number_input("하루 최대 트레이드 수", min_value=1, max_value=20, value=int(st.session_state.daily_trade_limit), step=1)
    with right:
        add_loss = st.number_input("오늘 추가 손실 입력 (%)", min_value=0.0, max_value=100.0, value=0.0, step=0.1)
        if st.button("손실 누적 반영"):
            st.session_state.daily_loss_used_pct += add_loss
            st.success("오늘 손실 누적 반영 완료")
        if st.button("트레이드 1회 사용 처리"):
            st.session_state.daily_trades_used += 1
            st.success("오늘 트레이드 수 반영 완료")
        if st.button("오늘 기록 초기화"):
            st.session_state.daily_loss_used_pct = 0.0
            st.session_state.daily_trades_used = 0
            st.success("오늘 기록 초기화 완료")
    locked = (
        st.session_state.daily_loss_used_pct >= st.session_state.daily_loss_limit_pct or
        st.session_state.daily_trades_used >= st.session_state.daily_trade_limit
    )
    if locked:
        st.error("오늘은 종료다. 손실 한도 또는 트레이드 한도를 넘었다.")
    else:
        st.success("오늘 거래 가능. 그래도 A급 외 진입 금지.")
    st.markdown("#### 실수 재발 경고")
    warns = recent_warnings(st.session_state.journal)
    if warns:
        for w in warns:
            st.warning(w)
    else:
        st.info("최근 재발 경고는 아직 없다.")

with tabs[1]:
    st.subheader("ULTRA 이미지 엔진")
    st.caption("차트 업로드 → 자동 인터뷰 → 진입 허가/관찰/금지 → 양방향 시나리오")
    uploaded = st.file_uploader("트레이딩뷰 캡처 업로드", type=["png","jpg","jpeg","webp"])
    l1, l2 = st.columns(2)
    with l1:
        symbol = st.text_input("종목", value="BTCUSDT")
        timeframe = st.selectbox("시간봉", ["15M","1H","4H","1D"], index=1)
        direction = st.selectbox("방향 후보", ["Long","Short"])
        pattern = st.selectbox("하모닉 패턴 후보", ["없음","샤크","딥크랩","크랩","배트","가틀리","나비"])
    with l2:
        rsi = st.selectbox("RSI 상태", ["모름","과매도 근처","과매수 근처","50 위","50 아래","다이버전스 의심"])
        stop_type = st.selectbox("생각 중인 손절 방식", ["미정","D 아래","HL/LH 아래","구조 무효화 지점"])
        eth_state = st.selectbox("ETH 상태", ["모름","같은 방향","약함","반대 신호"])
        notes = st.text_area("추가 메모", value="")
    if uploaded is not None:
        st.image(uploaded, caption="업로드한 차트", use_container_width=True)
    st.markdown("### 자동 인터뷰")
    q1, q2, q3, q4, q5 = st.columns(5)
    with q1:
        structure = st.checkbox("구조 깨짐 확인")
        pullback = st.checkbox("눌림/반등 확인")
    with q2:
        hl_lh = st.checkbox("HL/LH 확인")
        rebreak = st.checkbox("재돌파/재이탈 확인")
    with q3:
        prz = st.checkbox("D/PRZ 반응 확인")
        candle = st.checkbox("트리거 캔들 확인")
    with q4:
        stop_clarity = st.checkbox("손절 기준 명확")
        rr = st.checkbox("손익비 1:2 이상")
    with q5:
        eth_align = st.checkbox("ETH도 같은 방향")
        candle_closed = st.checkbox("봉 마감 확인")
    interview_score = sum([structure,pullback,hl_lh,rebreak,prz,candle,stop_clarity,rr,eth_align,candle_closed])
    decision, grade, reasons = ultra_decision(interview_score, structure, hl_lh, stop_clarity, rr, eth_align, candle_closed)
    st.session_state.last_grade = grade
    r1, r2, r3 = st.columns(3)
    r1.metric("ULTRA 점수", f"{interview_score}/10")
    r2.metric("등급", grade)
    r3.metric("최종 판정", decision)
    if decision == "진입 허가":
        st.success("✅ 진입 허가: 그래도 추격은 금지하고 포지션 계산기로 리스크부터 맞춰라.")
    elif decision == "관찰만":
        st.warning("🟡 관찰만: 아직 확정 부족. 더 기다리는 게 맞다.")
    else:
        st.error("⛔ 진입 금지")
    st.markdown("#### 판정 이유")
    if reasons:
        for r in reasons:
            st.write(f"- {r}")
    else:
        st.write("- 핵심 체크 조건 통과")
    if pattern != "없음":
        st.info(f"패턴 후보: {pattern} / RSI: {rsi} / 손절 방식: {stop_type}")
    st.markdown("#### 양방향 시나리오")
    st.text_area("시나리오", value=scenario_text(symbol, direction, structure, hl_lh, rebreak, prz), height=160)
    memo = f"{pattern} 후보, RSI {rsi}, ETH {eth_state}, 판정 {decision}. {notes}"
    st.text_area("이미지 기반 X 초안", value=make_x_post(symbol, timeframe, direction, grade, 0, 0, 0, 0, memo), height=180)

with tabs[2]:
    st.subheader("진입 판정기")
    score = sum([
        st.checkbox("구조 깨짐 확인", key="j_s"),
        st.checkbox("눌림/반등 확인", key="j_p"),
        st.checkbox("D/PRZ 반응", key="j_d"),
        st.checkbox("HL/LH 형성", key="j_h"),
        st.checkbox("재돌파/재이탈", key="j_r"),
        st.checkbox("트리거 캔들 존재", key="j_t"),
        st.checkbox("RSI 보조 확인", key="j_i"),
        st.checkbox("손절 기준 명확", key="j_c"),
        st.checkbox("손익비 1:2 이상", key="j_rr"),
    ])
    grade2, action2 = grade_logic(score)
    a1, a2, a3 = st.columns(3)
    a1.metric("체크 점수", f"{score}/9")
    a2.metric("등급", grade2)
    a3.metric("행동", action2)

with tabs[3]:
    st.subheader("포지션 계산기")
    c1, c2 = st.columns(2)
    with c1:
        bal2 = st.number_input("계좌 잔고 (USDT)", min_value=0.0, value=1000.0, step=100.0)
        risk2 = st.number_input("리스크 (%)", min_value=0.1, max_value=100.0, value=3.0, step=0.5)
        dir2 = st.selectbox("방향", ["Long","Short"])
        maxlev2 = st.number_input("최대 허용 레버리지", min_value=1, max_value=200, value=20, step=1)
    with c2:
        entry2 = st.number_input("진입가", min_value=0.0, value=70000.0, step=10.0)
        stop2 = st.number_input("손절가", min_value=0.0, value=69300.0, step=10.0)
        tp12 = st.number_input("TP1", min_value=0.0, value=71200.0, step=10.0)
        tp22 = st.number_input("TP2", min_value=0.0, value=71800.0, step=10.0)
        fee2 = st.number_input("수수료 추정 (%)", min_value=0.0, value=0.10, step=0.01)
    res = calc_trade(bal2, risk2, dir2, entry2, stop2, tp12, tp22, maxlev2, fee2)
    m1, m2, m3 = st.columns(3)
    m1.metric("허용 손실금액", f"${res.get('risk_amount', 0):,.2f}")
    m2.metric("손절폭", f"{res.get('stop_pct', 0):.3f}%")
    m3.metric("상태", res["status"])
    if "position_notional" in res:
        m4, m5, m6 = st.columns(3)
        m4.metric("권장 포지션 규모", f"${res['position_notional']:,.2f}")
        m5.metric("권장 수량", f"{res['qty']:.6f}")
        m6.metric("필요 레버리지", f"{res['required_lev']:.2f}x")

with tabs[4]:
    st.subheader("복리 추적기")
    start_balance = st.number_input("시작 금액", min_value=1.0, value=1000.0, step=100.0)
    avg_return = st.number_input("평균 수익률 (% / 회차)", min_value=-100.0, value=2.0, step=0.1)
    periods = st.slider("시뮬레이션 횟수", min_value=1, max_value=300, value=100)
    balances = [start_balance]
    for _ in range(periods):
        balances.append(balances[-1] * (1 + avg_return / 100.0))
    st.line_chart(pd.DataFrame({"회차": list(range(len(balances))), "잔고": balances}).set_index("회차"))

with tabs[5]:
    st.subheader("매매일지")
    j1, j2, j3 = st.columns(3)
    with j1:
        j_date = st.date_input("날짜", value=date.today())
        j_symbol = st.text_input("종목명", value="BTCUSDT")
    with j2:
        j_tf = st.selectbox("시간봉", ["15M","1H","4H","1D"], index=1, key="journal_tf")
        j_dir = st.selectbox("방향", ["Long","Short"], key="j_dir")
    with j3:
        j_grade = st.selectbox("자리 등급", ["A급","B급","쓰레기"])
        j_score = st.number_input("체크 점수", min_value=0, max_value=10, value=7, step=1)
    j_result = st.number_input("결과(%)", value=0.0, step=0.1)
    j_mistake = st.selectbox("실수 유형", ["없음","손절 늦음","HL 전 선진입","추격 진입","RSI만 보고 진입","손절 기준 불명확","기타"])
    j_rule = st.selectbox("원칙 준수", ["예","아니오"])
    j_notes = st.text_area("메모", value="")
    if st.button("매매일지 추가"):
        new_row = pd.DataFrame([{
            "날짜": str(j_date), "종목": j_symbol, "시간봉": j_tf, "방향": j_dir,
            "자리등급": j_grade, "체크점수": j_score, "결과(%)": j_result,
            "실수유형": j_mistake, "원칙준수": j_rule, "메모": j_notes
        }])
        st.session_state.journal = pd.concat([st.session_state.journal, new_row], ignore_index=True)
        st.success("매매일지 추가 완료")
    st.dataframe(st.session_state.journal, use_container_width=True, height=300)

with tabs[6]:
    st.subheader("통계")
    if st.session_state.journal.empty:
        st.info("아직 매매일지가 없다.")
    else:
        stats_df = st.session_state.journal.copy()
        stats_df["결과(%)"] = pd.to_numeric(stats_df["결과(%)"], errors="coerce").fillna(0)
        c1, c2, c3 = st.columns(3)
        c1.metric("총 트레이드", f"{len(stats_df)}")
        c2.metric("승률", f"{((stats_df['결과(%)'] > 0).sum() / len(stats_df) * 100):.1f}%")
        c3.metric("평균 결과", f"{stats_df['결과(%)'].mean():.2f}%")
        st.dataframe(stats_df.groupby("자리등급")["결과(%)"].agg(["count","mean"]), use_container_width=True)
        st.bar_chart(stats_df["실수유형"].value_counts())

with tabs[7]:
    st.subheader("X 게시물 생성기")
    p_symbol = st.text_input("종목", value="BTC", key="post_symbol")
    p_tf = st.selectbox("시간봉", ["15M","1H","4H","1D"], index=1, key="post_tf")
    p_dir = st.selectbox("방향", ["Long","Short"], key="post_dir")
    p_grade = st.selectbox("자리 등급", ["A급","B급","쓰레기"], index=0, key="post_grade")
    p_entry = st.number_input("진입가", min_value=0.0, value=70000.0, step=10.0, key="post_entry")
    p_stop = st.number_input("손절가", min_value=0.0, value=69300.0, step=10.0, key="post_stop")
    p_tp1 = st.number_input("TP1", min_value=0.0, value=71200.0, step=10.0, key="post_tp1")
    p_tp2 = st.number_input("TP2", min_value=0.0, value=71800.0, step=10.0, key="post_tp2")
    p_notes = st.text_area("게시물 메모", value="구조 깨짐 후 눌림 확인, 추격은 금지.", key="post_notes")
    st.text_area("생성된 게시물", value=make_x_post(p_symbol, p_tf, p_dir, p_grade, p_entry, p_stop, p_tp1, p_tp2, p_notes), height=220)

st.divider()
st.caption("면책: 이 앱은 투자 자문이 아니라 리스크 관리, 계획 수립, 복기, 규율 유지 보조 도구입니다.")
