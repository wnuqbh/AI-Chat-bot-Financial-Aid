import type { Holding, Quote } from './api'

export interface HoldingSummary {
  holding: Holding
  quote: Quote | null
  costBasis: number
  /** Market value at the live price, or the cost basis when there's no price. */
  value: number
  /** Unrealized gain; null without a live price. */
  gain: number | null
  gainPercent: number | null
  dayChangePercent: number | null
  /** Share of the portfolio's total value, 0–100. */
  weight: number
}

export interface PortfolioSummary {
  rows: HoldingSummary[]
  totalCost: number
  totalValue: number
  /** Gain across holdings that have a live price; null if none do. */
  totalGain: number | null
  totalGainPercent: number | null
  /** True when every holding has a live price, so totalValue is fully market-based. */
  fullyPriced: boolean
}

export function summarizePortfolio(holdings: Holding[], quotes: Record<string, Quote | null>): PortfolioSummary {
  const base = holdings.map((holding) => {
    const quote = quotes[holding.symbol] ?? null
    const quantity = Number(holding.quantity)
    const costBasis = quantity * Number(holding.average_cost)
    const value = quote ? quantity * quote.price : costBasis
    const gain = quote ? value - costBasis : null
    return {
      holding,
      quote,
      costBasis,
      value,
      gain,
      gainPercent: gain !== null && costBasis > 0 ? (gain / costBasis) * 100 : null,
      dayChangePercent:
        quote?.previous_close ? ((quote.price - quote.previous_close) / quote.previous_close) * 100 : null,
    }
  })

  const totalValue = base.reduce((sum, r) => sum + r.value, 0)
  const totalCost = base.reduce((sum, r) => sum + r.costBasis, 0)
  const priced = base.filter((r) => r.gain !== null)
  const pricedCost = priced.reduce((sum, r) => sum + r.costBasis, 0)
  const totalGain = priced.length ? priced.reduce((sum, r) => sum + (r.gain ?? 0), 0) : null

  return {
    rows: base
      .map((r) => ({ ...r, weight: totalValue > 0 ? (r.value / totalValue) * 100 : 0 }))
      .sort((a, b) => a.holding.symbol.localeCompare(b.holding.symbol)),
    totalCost,
    totalValue,
    totalGain,
    totalGainPercent: totalGain !== null && pricedCost > 0 ? (totalGain / pricedCost) * 100 : null,
    fullyPriced: holdings.length > 0 && priced.length === holdings.length,
  }
}
