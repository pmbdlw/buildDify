// 统一的 loading / 空态 / 错误提示,四模块复用。

export function PageLoading({ text = '加载中…', full }: { text?: string; full?: boolean }) {
  return (
    <div
      className={
        full ? 'grid h-screen place-items-center text-gray-400' : 'py-20 text-center text-gray-400'
      }
    >
      <span className="inline-flex items-center gap-2">
        <Spinner />
        {text}
      </span>
    </div>
  )
}

export function EmptyState({ text }: { text: string }) {
  return <p className="mt-16 text-center text-gray-400">{text}</p>
}

export function ErrorBanner({ message }: { message: string }) {
  if (!message) return null
  return (
    <div className="mb-4 rounded-lg border border-red-100 bg-red-50 px-4 py-2 text-sm text-red-600">
      ⚠️ {message}
    </div>
  )
}

export function Spinner() {
  return (
    <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-gray-300 border-t-gray-700" />
  )
}
