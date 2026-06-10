/**
 * technicalInsights.js — 规则型技术面解读，纯函数无副作用。
 * 仅描述价格与指标的当前状态，不含任何投资建议。
 *
 * level 枚举：
 *   positive — 偏强
 *   neutral  — 震荡 / 中性
 *   warning  — 偏弱
 *   limited  — 数据不足
 */

/**
 * 趋势解读：最新收盘价与 MA5 / MA20 对比。
 *
 * @param {{ candles: {time,open,high,low,close}[] }} klineData
 * @param {{ ma5: {time,value}[], ma20: {time,value}[] }} maData
 * @returns {{ level: string, title: string, message: string }}
 */
export function buildTrendInsight(klineData, maData) {
  const candles = klineData?.candles || []
  const ma5     = maData?.ma5  || []
  const ma20    = maData?.ma20 || []

  if (!candles.length || !ma5.length || !ma20.length) {
    return { level: 'limited', title: '趋势', message: '数据不足，暂无法生成趋势解读。' }
  }

  const lastClose = candles[candles.length - 1].close
  const lastMa5   = ma5[ma5.length - 1].value
  const lastMa20  = ma20[ma20.length - 1].value

  if (!Number.isFinite(lastClose) || !Number.isFinite(lastMa5) || !Number.isFinite(lastMa20)) {
    return { level: 'limited', title: '趋势', message: '数据不足，暂无法生成趋势解读。' }
  }

  const aboveMa5  = lastClose > lastMa5
  const aboveMa20 = lastClose > lastMa20

  if (aboveMa5 && aboveMa20) {
    return {
      level:   'positive',
      title:   '趋势',
      message: `收盘价（${lastClose.toFixed(2)}）位于 MA5（${lastMa5.toFixed(2)}）与 MA20（${lastMa20.toFixed(2)}）上方，短中期趋势偏强。`,
    }
  }

  if (!aboveMa5 && !aboveMa20) {
    return {
      level:   'warning',
      title:   '趋势',
      message: `收盘价（${lastClose.toFixed(2)}）位于 MA5（${lastMa5.toFixed(2)}）与 MA20（${lastMa20.toFixed(2)}）下方，短中期趋势偏弱。`,
    }
  }

  return {
    level:   'neutral',
    title:   '趋势',
    message: `收盘价（${lastClose.toFixed(2)}）处于 MA5（${lastMa5.toFixed(2)}）与 MA20（${lastMa20.toFixed(2)}）之间，趋势震荡，仍需观察。`,
  }
}

/**
 * 量能解读：近 5 日均量 vs 近 20 日均量，阈值 1.2 / 0.8。
 *
 * @param {{ candles: {close,volume?}[], volumes: {value}[] }} klineData
 * @returns {{ level: string, title: string, message: string }}
 */
export function buildVolumeInsight(klineData) {
  const volumes = klineData?.volumes || []
  const candles = klineData?.candles || []

  // Prefer pre-transformed volumes array; fall back to candle.volume field
  const rawVols = volumes.length
    ? volumes.map(v => v.value)
    : candles.map(c => c.volume ?? 0)

  const valid = rawVols.filter(v => Number.isFinite(v) && v > 0)

  if (valid.length < 20) {
    return { level: 'limited', title: '量能', message: '数据不足，暂无法计算成交量均值对比（至少需要 20 根K线）。' }
  }

  const recent5  = valid.slice(-5).reduce((a, b) => a + b, 0) / 5
  const recent20 = valid.slice(-20).reduce((a, b) => a + b, 0) / 20

  if (recent20 === 0) {
    return { level: 'limited', title: '量能', message: '成交量数据异常，暂无法生成量能解读。' }
  }

  const ratio = recent5 / recent20

  if (ratio >= 1.2) {
    return {
      level:   'positive',
      title:   '量能',
      message: `近 5 日均量（${_fmtVol(recent5)}）较近 20 日均量（${_fmtVol(recent20)}）放大，比值约 ${ratio.toFixed(2)}，量能偏强。`,
    }
  }

  if (ratio <= 0.8) {
    return {
      level:   'warning',
      title:   '量能',
      message: `近 5 日均量（${_fmtVol(recent5)}）较近 20 日均量（${_fmtVol(recent20)}）萎缩，比值约 ${ratio.toFixed(2)}，量能偏弱。`,
    }
  }

  return {
    level:   'neutral',
    title:   '量能',
    message: `近 5 日均量与近 20 日均量基本持平（比值 ${ratio.toFixed(2)}），量能震荡，仍需观察。`,
  }
}

/**
 * MACD 解读：histogram 正负 + 扩张/收窄方向。
 *
 * @param {{ time: string, dif: number, dea: number, histogram: number }[]} macdData
 * @returns {{ level: string, title: string, message: string }}
 */
export function buildMacdInsight(macdData) {
  if (!macdData || macdData.length < 2) {
    return { level: 'limited', title: 'MACD', message: 'K线数量不足，暂无法计算 MACD（至少需要 34 根K线）。' }
  }

  const last = macdData[macdData.length - 1]
  const prev = macdData[macdData.length - 2]
  const { dif, dea, histogram } = last

  if (!Number.isFinite(dif) || !Number.isFinite(dea) || !Number.isFinite(histogram)) {
    return { level: 'limited', title: 'MACD', message: '数据不足，暂无法生成 MACD 解读。' }
  }

  const aboveZero = histogram > 0
  const expanding = Math.abs(histogram) > Math.abs(prev.histogram)

  if (aboveZero && expanding) {
    return {
      level:   'positive',
      title:   'MACD',
      message: `DIF（${dif.toFixed(3)}）位于 DEA（${dea.toFixed(3)}）上方，柱状线为正且扩张，动能偏强。`,
    }
  }

  if (aboveZero && !expanding) {
    return {
      level:   'neutral',
      title:   'MACD',
      message: `DIF（${dif.toFixed(3)}）位于 DEA（${dea.toFixed(3)}）上方，柱状线为正但收窄，动能震荡，仍需观察。`,
    }
  }

  if (!aboveZero && !expanding) {
    return {
      level:   'warning',
      title:   'MACD',
      message: `DIF（${dif.toFixed(3)}）位于 DEA（${dea.toFixed(3)}）下方，柱状线为负且收窄，动能偏弱。`,
    }
  }

  // histogram < 0 and expanding (more negative)
  return {
    level:   'warning',
    title:   'MACD',
    message: `DIF（${dif.toFixed(3)}）位于 DEA（${dea.toFixed(3)}）下方，柱状线为负且扩张，短期动能偏弱。`,
  }
}

/**
 * RSI 解读：70 超买 / 30 超卖 / 50 中轴。
 *
 * @param {{ time: string, value: number }[]} rsiData
 * @returns {{ level: string, title: string, message: string }}
 */
export function buildRsiInsight(rsiData) {
  if (!rsiData || rsiData.length === 0) {
    return { level: 'limited', title: 'RSI', message: 'K线数量不足，暂无法计算 RSI（至少需要 15 根K线）。' }
  }

  const val = rsiData[rsiData.length - 1].value

  if (!Number.isFinite(val)) {
    return { level: 'limited', title: 'RSI', message: '数据不足，暂无法生成 RSI 解读。' }
  }

  if (val >= 70) {
    return {
      level:   'warning',
      title:   'RSI',
      message: `RSI(14) 当前值 ${val.toFixed(1)}，处于超买区域（≥ 70），短期偏强，注意过热风险。`,
    }
  }

  if (val <= 30) {
    return {
      level:   'warning',
      title:   'RSI',
      message: `RSI(14) 当前值 ${val.toFixed(1)}，处于超卖区域（≤ 30），短期偏弱，注意超跌可能性。`,
    }
  }

  if (val >= 50) {
    return {
      level:   'positive',
      title:   'RSI',
      message: `RSI(14) 当前值 ${val.toFixed(1)}，位于中轴上方（50~70），动能中性偏强。`,
    }
  }

  return {
    level:   'neutral',
    title:   'RSI',
    message: `RSI(14) 当前值 ${val.toFixed(1)}，位于中轴下方（30~50），动能中性偏弱，仍需观察。`,
  }
}

/**
 * 汇总入口：组合 4 个维度，生成 summary 摘要文字（不含投资建议）。
 *
 * @param {{ klineData, maData, macdData, rsiData }} params
 * @returns {{ trend, volume, macd, rsi, summary: string }}
 */
export function buildTechnicalInsightSummary({ klineData, maData, macdData, rsiData }) {
  const trend  = buildTrendInsight(klineData, maData)
  const volume = buildVolumeInsight(klineData)
  const macd   = buildMacdInsight(macdData)
  const rsi    = buildRsiInsight(rsiData)

  const all           = [trend, volume, macd, rsi]
  const positiveCount = all.filter(i => i.level === 'positive').length
  const warningCount  = all.filter(i => i.level === 'warning').length
  const limitedCount  = all.filter(i => i.level === 'limited').length

  let summary
  if (limitedCount >= 3) {
    summary = 'K线数量不足，多项指标无法计算，当前技术面解读有限。'
  } else if (positiveCount >= 3) {
    summary = '多项技术指标偏强，价格处于相对强势区间。具体信号以各维度解读为准。'
  } else if (warningCount >= 3) {
    summary = '多项技术指标偏弱，价格处于相对弱势区间。具体信号以各维度解读为准。'
  } else if (positiveCount > warningCount) {
    summary = '技术面整体偏强，但存在部分分歧，仍需结合更多信息综合判断。'
  } else if (warningCount > positiveCount) {
    summary = '技术面整体偏弱，但存在部分分歧，仍需结合更多信息综合判断。'
  } else {
    summary = '技术面多维信号混合，整体震荡，仍需观察后续走势。'
  }

  return { trend, volume, macd, rsi, summary }
}

// ── Internal formatter ────────────────────────────────────────────────────────
function _fmtVol(val) {
  if (!Number.isFinite(val)) return '—'
  if (val >= 1e8) return (val / 1e8).toFixed(1) + '亿'
  if (val >= 1e4) return (val / 1e4).toFixed(0) + '万'
  return Math.round(val).toLocaleString()
}
