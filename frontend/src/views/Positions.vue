<template>
  <div>
    <el-card>
	      <template #header>
	        <div style="display:flex;justify-content:space-between;align-items:center">
	          <span>持仓总览</span>
	          <div>
	            <el-button size="small" type="warning" @click="notifyDoctor" :loading="notifyLoading">推送复盘</el-button>
	            <el-button size="small" type="primary" @click="loadDoctor" :loading="doctorLoading">仓位医生</el-button>
	            <el-button size="small" @click="load" :loading="loading">刷新</el-button>
	          </div>
	        </div>
	      </template>
	      <el-descriptions :column="3" border size="small">
	        <el-descriptions-item label="USDC 余额">${{ usdcBalance }}</el-descriptions-item>
	        <el-descriptions-item label="持仓数量">{{ positions.length }}</el-descriptions-item>
	        <el-descriptions-item label="持仓总值">${{ totalValue }}</el-descriptions-item>
	      </el-descriptions>
	      <div v-if="doctor" style="margin-top:16px">
	        <el-alert :type="doctorAlertType" show-icon :closable="false" style="margin-bottom:12px">
	          <template #title>
	            仓位医生：{{ doctor.summary?.verdict }}，风险 {{ doctor.summary?.risk_level }}；高风险 {{ doctor.summary?.risk_counts?.high || 0 }}，阻断 {{ doctor.summary?.risk_counts?.critical || 0 }}
	          </template>
	          <template #default>
	            {{ (doctor.actions || []).join('；') }}
	          </template>
	        </el-alert>
	        <el-row :gutter="12" style="margin-bottom:12px">
	          <el-col :span="8">
	            <el-card shadow="never" class="doctor-card">
	              <div class="doctor-num">${{ Number(doctor.summary?.unrealized_pnl || 0).toFixed(2) }}</div>
	              <div class="doctor-label">持仓浮盈亏</div>
	            </el-card>
	          </el-col>
	          <el-col :span="8">
	            <el-card shadow="never" class="doctor-card">
	              <div class="doctor-num">{{ doctor.trade_review?.trades_24h || 0 }}</div>
	              <div class="doctor-label">24h 交易</div>
	            </el-card>
	          </el-col>
	          <el-col :span="8">
	            <el-card shadow="never" class="doctor-card">
	              <div class="doctor-num">${{ Number(doctor.trade_review?.realized_pnl_7d || 0).toFixed(2) }}</div>
	              <div class="doctor-label">7d 已实现</div>
	            </el-card>
	          </el-col>
	        </el-row>
	        <el-table :data="doctor.top_risks || []" size="small" max-height="260" style="margin-bottom:12px">
	          <el-table-column label="高风险持仓" show-overflow-tooltip>
	            <template #default="{ row }">{{ row.title_zh || row.title }}</template>
	          </el-table-column>
	          <el-table-column label="风险" width="80">
	            <template #default="{ row }"><el-tag :type="riskTagType(row.risk_level)" size="small">{{ row.risk_level }}</el-tag></template>
	          </el-table-column>
	          <el-table-column label="价值" width="90">
	            <template #default="{ row }">${{ Number(row.current_value || 0).toFixed(2) }}</template>
	          </el-table-column>
	          <el-table-column label="问题" show-overflow-tooltip>
	            <template #default="{ row }">{{ (row.blockers?.[0] || row.warnings?.[0] || row.actions?.[0] || '-') }}</template>
	          </el-table-column>
	          <el-table-column label="退出买盘" width="105">
	            <template #default="{ row }">${{ Number(row.exit_depth?.sellable_value || 0).toFixed(2) }}</template>
	          </el-table-column>
	        </el-table>
	      </div>
	      <el-table :data="positions" size="small" v-loading="loading" style="margin-top:16px">
        <el-table-column label="市场" show-overflow-tooltip>
          <template #default="{ row }">{{ row.title_zh || row.title }}</template>
        </el-table-column>
        <el-table-column label="到期 (北京)" width="120">
          <template #default="{ row }">{{ row.endDate_bj || row.endDateIso_bj || '-' }}</template>
        </el-table-column>
        <el-table-column prop="size" label="数量" width="100" />
        <el-table-column label="当前价值" width="120">
          <template #default="{ row }">${{ parseFloat(row.currentValue || 0).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="买入均价" width="100">
          <template #default="{ row }">${{ parseFloat(row.avgPrice || 0).toFixed(3) }}</template>
        </el-table-column>
        <el-table-column label="盈亏" width="100">
          <template #default="{ row }">
            <span :style="{ color: parseFloat(row.cashPnl || 0) >= 0 ? '#67c23a' : '#f56c6c' }">
              ${{ parseFloat(row.cashPnl || 0).toFixed(2) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="盈亏%" width="80">
          <template #default="{ row }">
            <span :style="{ color: parseFloat(row.percentPnl || 0) >= 0 ? '#67c23a' : '#f56c6c' }">
              {{ parseFloat(row.percentPnl || 0).toFixed(1) }}%
            </span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { btcApi } from '../api'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const doctorLoading = ref(false)
const notifyLoading = ref(false)
const positions = ref<any[]>([])
const balance = ref<any>(null)
const doctor = ref<any>(null)

const usdcBalance = computed(() => {
  if (!balance.value) return '--'
  const raw = balance.value.balance ?? balance.value.available ?? balance.value.available_balance ?? null
  return raw !== null ? Number(raw).toFixed(2) : '--'
})

const totalValue = computed(() => {
  return positions.value.reduce((sum, p) => sum + parseFloat(p.currentValue || 0), 0).toFixed(2)
})

const doctorAlertType = computed(() => {
  const level = doctor.value?.summary?.risk_level
  if (level === 'critical' || level === 'high') return 'error'
  if (level === 'medium') return 'warning'
  return 'success'
})

function riskTagType(level: string) {
  if (level === 'critical' || level === 'high') return 'danger'
  if (level === 'medium') return 'warning'
  return 'success'
}

async function load() {
  loading.value = true
  try {
    const { data } = await btcApi.positions()
    positions.value = data.positions || []
    balance.value = data.balance
  } catch {} finally { loading.value = false }
}

async function loadDoctor() {
  doctorLoading.value = true
  try {
    const { data } = await btcApi.portfolioDoctor()
    doctor.value = data
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || err?.message || '仓位医生失败')
  } finally { doctorLoading.value = false }
}

async function notifyDoctor() {
  notifyLoading.value = true
  try {
    const { data } = await btcApi.notifyPortfolioDoctor()
    ElMessage.success(data.message || '已推送复盘')
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || err?.message || '推送失败')
  } finally { notifyLoading.value = false }
}

onMounted(() => {
  load()
  loadDoctor()
})
</script>

<style scoped>
.doctor-card {
  text-align: center;
}

.doctor-num {
  font-size: 18px;
  font-weight: 700;
  color: #303133;
}

.doctor-label {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
</style>
