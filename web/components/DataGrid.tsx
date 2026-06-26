'use client'

// AG Grid 社区版薄封装:统一注册社区模块 + Quartz 主题 + 默认列行为(排序/筛选/自适应)。
// 仅用社区版功能(排序、列筛选、分页),不引入任何企业版模块。
import { useMemo } from 'react'
import {
  AllCommunityModule,
  type ColDef,
  ModuleRegistry,
  themeQuartz,
} from 'ag-grid-community'
import { AgGridReact } from 'ag-grid-react'

ModuleRegistry.registerModules([AllCommunityModule])

const theme = themeQuartz.withParams({
  accentColor: '#111827',
  fontFamily: 'inherit',
  headerFontWeight: 600,
  borderRadius: 8,
  wrapperBorderRadius: 12,
})

export interface DataGridProps<T> {
  rowData: T[]
  columnDefs: ColDef<T>[]
  onRowClicked?: (row: T) => void
  height?: number | string
  pageSize?: number
}

export default function DataGrid<T>({
  rowData,
  columnDefs,
  onRowClicked,
  height = 480,
  pageSize = 20,
}: DataGridProps<T>) {
  const defaultColDef = useMemo<ColDef<T>>(
    () => ({ sortable: true, filter: true, resizable: true, flex: 1, minWidth: 100 }),
    [],
  )
  return (
    <div style={{ height, width: '100%' }}>
      <AgGridReact<T>
        theme={theme}
        rowData={rowData}
        columnDefs={columnDefs}
        defaultColDef={defaultColDef}
        pagination
        paginationPageSize={pageSize}
        paginationPageSizeSelector={[10, 20, 50]}
        animateRows
        rowClass={onRowClicked ? 'cursor-pointer' : undefined}
        onRowClicked={(e) => e.data && onRowClicked?.(e.data)}
      />
    </div>
  )
}
