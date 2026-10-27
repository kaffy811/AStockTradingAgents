import { describe, it, expect, vi } from 'vitest'
vi.mock('../api/http.js', () => ({ baseFetch: vi.fn() }))
import { baseFetch } from '../api/http.js'
import { getReport } from '../api/reports.js'
it('reopens stored report visuals without fetching a newer market snapshot', async () => {
  const visuals = { growth: [{label:'营业收入',value:2.42,as_of:'2026-09-30'}] }
  baseFetch.mockResolvedValue({id:'old',report_md:'原始报告',sections:{},report_metadata:{reader_mode:'beginner',visuals},agents:{technical:{status:'success'}},warnings:[]})
  const result = await getReport('old')
  expect(result.metadata.visuals).toBe(visuals)
  expect(result.metadata.agents.technical.status).toBe('success')
  expect(baseFetch).toHaveBeenCalledTimes(1)
  expect(baseFetch).toHaveBeenCalledWith('/reports/old')
})
