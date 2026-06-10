/**
 * technicalIndicators.js — 前端技术指标纯函数计算工具。
 * 无副作用，不修改输入数组，不引入第三方库。
 * 输入数据不足或含 NaN / Infinity 时安全返回空结果，不抛异常。
 */

/**
 * 安全数值检查 — NaN / Infinity 返回 null。
 * @param {*} val
 * @returns {number|null}
 */
export function safeNumber(val) {
  return Number.isFinite(val) ? val : null
}

/**
 * 指数移动平均（EMA），使用 SMA 种子初始化。
 * 返回长度与 values 相同的数组，前 period-1 个元素为 null。
 *
 * @param {number[]} values - 数值序列（从旧到新）
 * @param {number}   period - EMA 周期
 * @returns {Array<number|null>}
 */
export function calculateEMA(values, period) {
  if (!values || values.length < period) return []

  const k      = 2 / (period + 1)
  const result = new Array(values.length).fill(null)

  // 首个 EMA 使用前 period 个值的简单平均
  let sum = 0
  for (let i = 0; i < period; i++) sum += values[i]
  result[period - 1] = sum / period

  for (let i = period; i < values.length; i++) {
    result[i] = values[i] * k + result[i - 1] * (1 - k)
  }
  return result
}

/**
 * MACD 指标（fast EMA - slow EMA）。
 * 需要至少 fast + signal - 1 根K线（默认 12+9-1=20），推荐 slow+signal-1=34 根。
 *
 * @param {string[]} times  - 日期序列（与 closes 一一对应，从旧到新）
 * @param {number[]} closes - 收盘价序列
 * @param {number}   fast   - 快线周期，默认 12
 * @param {number}   slow   - 慢线周期，默认 26
 * @param {number}   signal - 信号线周期，默认 9
 * @returns {{ time: string, dif: number, dea: number, histogram: number }[]}
 */
export function calculateMACD(times, closes, fast = 12, slow = 26, signal = 9) {
  // 至少需要 slow + signal - 1 根数据才能输出第一个 MACD 点
  if (!closes || closes.length < slow + signal - 1) return []

  const emaFast = calculateEMA(closes, fast)
  const emaSlow = calculateEMA(closes, slow)

  // DIF = EMA(fast) - EMA(slow)，slow-1 之前为 null
  const difRaw = closes.map((_, i) => {
    if (emaFast[i] == null || emaSlow[i] == null) return null
    return emaFast[i] - emaSlow[i]
  })

  // 提取有效 DIF 序列，用于计算 DEA（信号线）
  const validDif = difRaw.filter(v => v !== null)
  if (validDif.length < signal) return []

  const deaOfValid = calculateEMA(validDif, signal)

  // 将 DEA 映射回原始时间轴
  const result = []
  let vi = 0   // validDif 的索引
  for (let i = 0; i < closes.length; i++) {
    if (difRaw[i] === null) continue          // 尚无 DIF
    const dea = deaOfValid[vi]
    if (dea != null) {                        // DEA 有效时才输出
      const dif = difRaw[i]
      const hist = dif - dea
      // 过滤异常数值
      if (Number.isFinite(dif) && Number.isFinite(dea) && Number.isFinite(hist)) {
        result.push({
          time:      times[i],
          dif:       parseFloat(dif.toFixed(4)),
          dea:       parseFloat(dea.toFixed(4)),
          histogram: parseFloat(hist.toFixed(4)),
        })
      }
    }
    vi++
  }
  return result
}

/**
 * RSI 指标（Wilder's Smoothed RSI）。
 * 需要至少 period + 1 根K线（默认 15）。
 *
 * @param {string[]} times  - 日期序列
 * @param {number[]} closes - 收盘价序列
 * @param {number}   period - RSI 周期，默认 14
 * @returns {{ time: string, value: number }[]}
 */
export function calculateRSI(times, closes, period = 14) {
  if (!closes || closes.length <= period) return []

  const result = []

  // 初始化：计算前 period 个涨跌的平均增益 / 平均损失
  let avgGain = 0
  let avgLoss = 0
  for (let i = 1; i <= period; i++) {
    const change = closes[i] - closes[i - 1]
    if (change > 0) avgGain += change
    else avgLoss += Math.abs(change)
  }
  avgGain /= period
  avgLoss /= period

  // 第一个 RSI 值（index = period）
  const firstRsi = avgLoss === 0
    ? 100
    : parseFloat((100 - 100 / (1 + avgGain / avgLoss)).toFixed(2))
  if (Number.isFinite(firstRsi)) {
    result.push({ time: times[period], value: firstRsi })
  }

  // Wilder 平滑法递推
  for (let i = period + 1; i < closes.length; i++) {
    const change = closes[i] - closes[i - 1]
    avgGain = (avgGain * (period - 1) + (change > 0 ? change : 0)) / period
    avgLoss = (avgLoss * (period - 1) + (change < 0 ? Math.abs(change) : 0)) / period

    const rsiVal = avgLoss === 0
      ? 100
      : parseFloat((100 - 100 / (1 + avgGain / avgLoss)).toFixed(2))

    if (Number.isFinite(rsiVal)) {
      result.push({ time: times[i], value: rsiVal })
    }
  }

  return result
}
