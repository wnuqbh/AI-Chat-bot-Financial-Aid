import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { ApiError, api, type Holding } from '../api'

const money = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })
const shares = new Intl.NumberFormat('en-US', { maximumFractionDigits: 6 })

const costBasis = (h: Holding) => Number(h.quantity) * Number(h.average_cost)

const inputClass =
  'w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20'

export default function PortfolioPage() {
  const [holdings, setHoldings] = useState<Holding[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .portfolio()
      .then(({ portfolio }) => setHoldings(portfolio.holdings))
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Could not load portfolio'))
  }, [])

  const total = holdings?.reduce((sum, h) => sum + costBasis(h), 0) ?? 0
  const sorted = holdings ? [...holdings].sort((a, b) => a.symbol.localeCompare(b.symbol)) : []

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-4xl px-4 py-8">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold">Portfolio</h1>
            <p className="mt-1 text-sm text-slate-500">
              The advisor uses these holdings to tailor its answers.{' '}
              <Link to="/chat" className="text-emerald-700 hover:underline">
                Ask about them →
              </Link>
            </p>
          </div>
        </div>

        {error && <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

        <div className="mb-6 grid gap-4 sm:grid-cols-2">
          <Stat label="Holdings" value={holdings ? String(holdings.length) : '–'} />
          <Stat label="Total cost basis" value={holdings ? money.format(total) : '–'} />
        </div>

        <AddHoldingForm onAdded={(h) => setHoldings((prev) => [...(prev ?? []), h])} />

        <div className="mt-6 overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm">
          {holdings === null ? (
            <p className="p-6 text-center text-sm text-slate-400">Loading…</p>
          ) : holdings.length === 0 ? (
            <p className="p-6 text-center text-sm text-slate-500">No holdings yet. Add your first one above.</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-4 py-3 font-medium">Symbol</th>
                  <th className="px-4 py-3 text-right font-medium">Shares</th>
                  <th className="px-4 py-3 text-right font-medium">Avg. cost</th>
                  <th className="px-4 py-3 text-right font-medium">Cost basis</th>
                  <th className="px-4 py-3 text-right font-medium">Weight</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {sorted.map((holding) => (
                  <HoldingRow
                    key={holding.id}
                    holding={holding}
                    total={total}
                    onUpdated={(h) => setHoldings((prev) => prev!.map((x) => (x.id === h.id ? h : x)))}
                    onDeleted={(id) => setHoldings((prev) => prev!.filter((x) => x.id !== id))}
                  />
                ))}
              </tbody>
            </table>
          )}
        </div>
        <p className="mt-3 text-xs text-slate-400">
          Cost basis and weights use the prices you paid. Live market prices aren't tracked yet.
        </p>
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
    </div>
  )
}

function AddHoldingForm({ onAdded }: { onAdded: (holding: Holding) => void }) {
  const [symbol, setSymbol] = useState('')
  const [quantity, setQuantity] = useState('')
  const [averageCost, setAverageCost] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setSaving(true)
    try {
      const { holding } = await api.addHolding(symbol.trim(), quantity, averageCost)
      onAdded(holding)
      setSymbol('')
      setQuantity('')
      setAverageCost('')
    } catch (err) {
      setError(err instanceof ApiError ? err.friendlyMessage : 'Could not add holding')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="mb-3 text-sm font-semibold">Add a holding</h2>
      <div className="grid gap-3 sm:grid-cols-[1fr_1fr_1fr_auto]">
        <input
          required
          placeholder="Symbol, e.g. VTI"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value.toUpperCase())}
          className={inputClass}
        />
        <input
          required
          type="number"
          step="any"
          min="0"
          placeholder="Shares"
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
          className={inputClass}
        />
        <input
          required
          type="number"
          step="any"
          min="0"
          placeholder="Avg. cost per share ($)"
          value={averageCost}
          onChange={(e) => setAverageCost(e.target.value)}
          className={inputClass}
        />
        <button
          type="submit"
          disabled={saving}
          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-60"
        >
          {saving ? 'Adding…' : 'Add'}
        </button>
      </div>
      {error && <p className="mt-3 text-sm text-red-700">{error}</p>}
    </form>
  )
}

function HoldingRow({
  holding,
  total,
  onUpdated,
  onDeleted,
}: {
  holding: Holding
  total: number
  onUpdated: (holding: Holding) => void
  onDeleted: (id: number) => void
}) {
  const [editing, setEditing] = useState(false)
  const [quantity, setQuantity] = useState('')
  const [averageCost, setAverageCost] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [confirmingDelete, setConfirmingDelete] = useState(false)

  function startEditing() {
    setQuantity(String(Number(holding.quantity)))
    setAverageCost(String(Number(holding.average_cost)))
    setError(null)
    setEditing(true)
  }

  async function save() {
    try {
      const { holding: updated } = await api.updateHolding(holding.id, quantity, averageCost)
      onUpdated(updated)
      setEditing(false)
    } catch (err) {
      setError(err instanceof ApiError ? err.friendlyMessage : 'Could not save')
    }
  }

  async function remove() {
    try {
      await api.deleteHolding(holding.id)
      onDeleted(holding.id)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not delete')
      setConfirmingDelete(false)
    }
  }

  const weight = total > 0 ? (costBasis(holding) / total) * 100 : 0
  const cellInput = 'w-28 rounded-md border border-slate-300 px-2 py-1 text-right text-sm outline-none focus:border-emerald-500'
  const textButton = 'rounded-md px-2 py-1 text-xs font-medium'

  return (
    <tr className="align-middle">
      <td className="px-4 py-3 font-semibold">
        {holding.symbol}
        {error && <p className="mt-1 text-xs font-normal text-red-700">{error}</p>}
      </td>
      {editing ? (
        <>
          <td className="px-4 py-2 text-right">
            <input type="number" step="any" min="0" value={quantity} onChange={(e) => setQuantity(e.target.value)} className={cellInput} />
          </td>
          <td className="px-4 py-2 text-right">
            <input type="number" step="any" min="0" value={averageCost} onChange={(e) => setAverageCost(e.target.value)} className={cellInput} />
          </td>
          <td colSpan={2} />
          <td className="whitespace-nowrap px-4 py-2 text-right">
            <button onClick={save} className={`${textButton} bg-emerald-600 text-white hover:bg-emerald-700`}>
              Save
            </button>
            <button onClick={() => setEditing(false)} className={`${textButton} text-slate-600 hover:bg-slate-100`}>
              Cancel
            </button>
          </td>
        </>
      ) : (
        <>
          <td className="px-4 py-3 text-right tabular-nums">{shares.format(Number(holding.quantity))}</td>
          <td className="px-4 py-3 text-right tabular-nums">{money.format(Number(holding.average_cost))}</td>
          <td className="px-4 py-3 text-right tabular-nums">{money.format(costBasis(holding))}</td>
          <td className="px-4 py-3 text-right tabular-nums text-slate-500">{weight.toFixed(1)}%</td>
          <td className="whitespace-nowrap px-4 py-3 text-right">
            {confirmingDelete ? (
              <>
                <button onClick={remove} className={`${textButton} bg-red-600 text-white hover:bg-red-700`}>
                  Delete
                </button>
                <button onClick={() => setConfirmingDelete(false)} className={`${textButton} text-slate-600 hover:bg-slate-100`}>
                  Keep
                </button>
              </>
            ) : (
              <>
                <button onClick={startEditing} className={`${textButton} text-slate-600 hover:bg-slate-100`}>
                  Edit
                </button>
                <button onClick={() => setConfirmingDelete(true)} className={`${textButton} text-slate-600 hover:bg-slate-100 hover:text-red-600`}>
                  Remove
                </button>
              </>
            )}
          </td>
        </>
      )}
    </tr>
  )
}
