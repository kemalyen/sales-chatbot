import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import axios from 'axios'
import { API_BASE_URL, clearToken, describeError } from './api'
import './Chat.css'

type Role = 'user' | 'assistant'

type Message = {
  id: number
  role: Role
  content: string
}

type CartItem = {
  sku: string
  name: string
  quantity: number
  unit_price: number
  line_total: number
}

type Cart = {
  items: CartItem[]
  item_count: number
  total: number
}

type ChatProps = {
  token: string
  onLogout: () => void
}

const MAX_MESSAGE_LENGTH = 2000

let nextId = 1

function formatMoney(value: number): string {
  return value.toFixed(2)
}

function Chat({ token, onLogout }: ChatProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [cart, setCart] = useState<Cart | null>(null)
  const [cartError, setCartError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const authHeaders = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token])

  const refreshCart = useCallback(async () => {
    try {
      const { data } = await axios.get<Cart>(`${API_BASE_URL}/api/cart`, {
        headers: authHeaders,
      })
      setCart(data)
      setCartError(null)
    } catch (caught) {
      setCart(null)
      setCartError(describeError(caught))
    }
  }, [authHeaders])

  useEffect(() => {
    // oxlint-disable-next-line react/set-state-in-effect -- mount-time fetch; every setState runs after the await
    refreshCart()
  }, [refreshCart])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [messages, sending])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const content = input.trim()
    if (!content || sending) {
      return
    }

    setMessages((current) => [
      ...current,
      { id: nextId++, role: 'user', content },
    ])
    setInput('')
    setSending(true)
    setError(null)

    let signedOut = false
    try {
      const { data } = await axios.post<{ reply: string }>(
        `${API_BASE_URL}/api/chat`,
        { message: content },
        { headers: authHeaders },
      )
      setMessages((current) => [
        ...current,
        { id: nextId++, role: 'assistant', content: data.reply },
      ])
    } catch (caught) {
      if (axios.isAxiosError(caught) && caught.response?.status === 401) {
        signedOut = true
        clearToken()
        onLogout()
        return
      }
      setError(describeError(caught))
      setMessages((current) => [
        ...current,
        { id: nextId++, role: 'assistant', content: describeError(caught) },
      ])
    } finally {
      setSending(false)
      if (!signedOut) {
        await refreshCart()
      }
    }
  }

  return (
    <div className="chat">
      <section className="chat-panel" aria-label="Conversation">
        <div className="chat-messages" role="log" aria-live="polite">
          {messages.length === 0 && (
            <p className="chat-empty">
              Ask about a product, or tell me what to put in your cart.
            </p>
          )}
          {messages.map((message) => (
            <div key={message.id} className={`chat-bubble chat-bubble--${message.role}`}>
              {message.content}
            </div>
          ))}
          {sending && <div className="chat-typing">Assistant is typing…</div>}
          <div ref={bottomRef} />
        </div>

        {error && (
          <p className="chat-error" role="alert">
            {error}
          </p>
        )}

        <form className="chat-composer" onSubmit={handleSubmit}>
          <label className="chat-label" htmlFor="chat-input">
            Message
          </label>
          <div className="chat-composer-row">
            <input
              id="chat-input"
              type="text"
              value={input}
              maxLength={MAX_MESSAGE_LENGTH}
              placeholder="I am looking for a wireless mouse…"
              onChange={(event) => setInput(event.target.value)}
              disabled={sending}
            />
            <button type="submit" disabled={sending || input.trim() === ''}>
              Send
            </button>
          </div>
        </form>
      </section>

      <aside className="cart-panel" aria-label="Shopping cart">
        <h2>Your cart</h2>

        {cartError && (
          <p className="chat-error" role="alert">
            {cartError}
          </p>
        )}

        {!cartError && cart && cart.item_count === 0 && (
          <p className="cart-empty">Your cart is empty.</p>
        )}

        {cart && cart.item_count > 0 && (
          <>
            <ul className="cart-items">
              {cart.items.map((item) => (
                <li key={item.sku} className="cart-item">
                  <div className="cart-item-head">
                    <span className="cart-item-name">{item.name}</span>
                    <span className="cart-item-sku">{item.sku}</span>
                  </div>
                  <div className="cart-item-meta">
                    <span>
                      {item.quantity} × {formatMoney(item.unit_price)}
                    </span>
                    <strong>{formatMoney(item.line_total)}</strong>
                  </div>
                </li>
              ))}
            </ul>
            <p className="cart-total">
              Total <strong>{formatMoney(cart.total)}</strong>
            </p>
          </>
        )}
      </aside>
    </div>
  )
}

export default Chat