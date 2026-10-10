import { describe, expect, it } from 'vitest'
import { summarizePortfolio } from './portfolio'

const holding = (id: number, symbol: string, quantity: string, average_cost: string) => ({ id, symbol, quantity, average_cost })

describe('summarizePortfolio', () => {
  it('values priced holdings at market and the rest at cost', () => {
    const summary = summarizePortfolio(
      [holding(1, 'VTI', '10', '200'), holding(2, 'XYZ', '5', '100')],
      { VTI: { price: 250, previous_close: 240, currency: 'USD' }, XYZ: null },
    )
    const [vti, xyz] = summary.rows

    expect(vti.value).toBe(2500)
    expect(vti.gain).toBe(500)
    expect(vti.gainPercent).toBe(25)
    expect(vti.dayChangePercent).toBeCloseTo(4.1667, 3)

    expect(xyz.value).toBe(500)
    expect(xyz.gain).toBeNull()

    expect(summary.totalValue).toBe(3000)
    expect(summary.totalCost).toBe(2500)
    // Gain only counts holdings with a price: 500 on VTI's 2000 cost.
    expect(summary.totalGain).toBe(500)
    expect(summary.totalGainPercent).toBe(25)
    expect(summary.fullyPriced).toBe(false)
    expect(vti.weight + xyz.weight).toBeCloseTo(100)
  })

  it('sorts rows by symbol and reports no gain without prices', () => {
    const summary = summarizePortfolio([holding(1, 'VTI', '1', '1'), holding(2, 'AAPL', '1', '1')], {})
    expect(summary.rows.map((r) => r.holding.symbol)).toEqual(['AAPL', 'VTI'])
    expect(summary.totalGain).toBeNull()
  })

  it('handles an empty portfolio', () => {
    const summary = summarizePortfolio([], {})
    expect(summary).toMatchObject({ rows: [], totalValue: 0, totalCost: 0, totalGain: null, fullyPriced: false })
  })
})
