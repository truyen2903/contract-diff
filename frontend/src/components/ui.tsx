import type { ButtonHTMLAttributes, PropsWithChildren, ReactNode } from 'react'
import { AlertTriangle, CheckCircle2, ChevronDown, FileText, LoaderCircle } from 'lucide-react'

export function Button({ children, variant = 'primary', className = '', ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'ghost' | 'danger' }) {
  return <button className={`button button-${variant} ${className}`} {...props}>{children}</button>
}

export function Card({ children, className = '' }: PropsWithChildren<{ className?: string }>) {
  return <section className={`card ${className}`}>{children}</section>
}

export function Badge({ children, tone = 'neutral' }: PropsWithChildren<{ tone?: string }>) {
  return <span className={`badge badge-${tone.toLowerCase()}`}>{children}</span>
}

export function Alert({ children, tone = 'warning' }: PropsWithChildren<{ tone?: 'warning' | 'danger' | 'success' }>) {
  const Icon = tone === 'success' ? CheckCircle2 : tone === 'danger' ? AlertTriangle : AlertTriangle
  return <div className={`alert alert-${tone}`} role={tone === 'danger' ? 'alert' : 'status'}><Icon size={17} aria-hidden="true" /><span>{children}</span></div>
}

export function EmptyState({ icon = <FileText size={24} />, title, children, action }: { icon?: ReactNode; title: string; children: ReactNode; action?: ReactNode }) {
  return <div className="empty-state"><div className="empty-icon">{icon}</div><h2>{title}</h2><p>{children}</p>{action}</div>
}

export function LoadingState() {
  return <div className="loading-state" role="status" aria-live="polite"><LoaderCircle className="spin" size={24} aria-hidden="true" /><span>Đang phân tích hai phiên bản…</span></div>
}

export function SelectChevron() { return <ChevronDown size={15} aria-hidden="true" /> }
