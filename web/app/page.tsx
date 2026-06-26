import Link from 'next/link'

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-gray-50 p-4">
      <div className="text-center">
        <h1 className="text-3xl font-bold text-gray-900">buildDify</h1>
        <p className="mt-2 text-gray-500">定制化 LLM 应用开发平台</p>
      </div>
      <Link
        href="/login"
        className="rounded-lg bg-gray-900 px-6 py-2.5 text-sm font-medium text-white hover:bg-gray-800"
      >
        进入控制台
      </Link>
    </main>
  )
}
