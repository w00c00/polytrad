<template>
  <div class="m-pos">
    <!-- Balance -->
    <div class="balance-bar">
      <div>
        <div class="bal-label">USDC 余额</div>
        <div class="bal-value">${{ usdcBalance }}</div>
      </div>
      <div>
        <div class="bal-label">持仓总值</div>
        <div class="bal-value">${{ totalValue }}</div>
      </div>
    </div>

    <!-- Positions -->
    <div class="pos-list">
      <div v-if="loading" class="empty-hint">加载中...</div>
      <div v-else-if="positions.length === 0" class="empty-hint">暂无持仓</div>
      <div v-for="p in positions" :key="p.asset" class="pos-card">
        <div class="pos-header">
          <div class="pos-title">{{ p.title_zh || p.title }}</div>
          <button class="sell-btn" :disabled="selling === p.asset" @click="quickSell(p)">
            {{ selling === p.asset ? '...' : '卖出' }}
          </button>
        </div>
        <div class="pos-detail">
          <div class="pos-item">
            <span class="pos-label">份额</span>
            <span class="pos-val">{{ p.size }}</span>
          </div>
          <div class="pos-item">
            <span class="pos-label">价值</span>
            <span class="pos-val">${{ parseFloat(p.currentValue || 0).toFixed(2) }}</span>
          </div>
          <div class="pos-item">
            <span class="pos-label">盈亏</span>
            <span class="pos-val" :class="{ profit: parseFloat(p.cashPnl || 0) >= 0, loss: parseFloat(p.cashPnl || 0) < 0 }">
              {{ parseFloat(p.cashPnl || 0) >= 0 ? '+' : '' }}${{ parseFloat(p.cashPnl || 0).toFixed(2) }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { btcApi } from '../../api'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const positions = ref<any[]>([])
const usdcBalance = ref('--')
const selling = ref('')

const totalValue = computed(() => {
  return positions.value.reduce((sum, p) => sum + parseFloat(p.currentValue || 0), 0).toFixed(2)
})

async function loadData() {
  loading.value = true
  try {
    const { data } = await btcApi.positions()
    positions.value = (data.positions || []).filter((p: any) => parseFloat(p.size || 0) > 0.000001 && !p.redeemable && !p.redeemed)
    const bal = data.balance
    if (bal && typeof bal === 'object') {
      const raw = bal.balance ?? bal.available ?? bal.available_balance ?? null
      usdcBalance.value = raw !== null ? Number(raw).toFixed(2) : '--'
    }
  } catch {} finally { loading.value = false }
}

async function quickSell(p: any) {
  const tokenId = p.asset
  if (!tokenId) { ElMessage.warning('无法获取 token'); return }
  const size = Math.floor(parseFloat(p.size || 0))
  if (size <= 0) { ElMessage.warning('持仓为 0'); return }
  selling.value = tokenId
  try {
    const { data } = await btcApi.sell({ token_id: tokenId, size })
    ElMessage.success(`挂卖单: ${size} 份 @ $${data.price}`)
    loadData()
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || err?.message || '卖出失败')
  } finally { selling.value = '' }
}

onMounted(loadData)
</script>

<style scoped>
.m-pos { padding: 12px; }

.balance-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
}

.balance-bar > div {
  flex: 1;
  background: linear-gradient(135deg, #304156, #409eff);
  color: #fff;
  border-radius: 10px;
  padding: 14px 16px;
}

.bal-label { font-size: 12px; opacity: 0.8; margin-bottom: 2px; }
.bal-value { font-size: 20px; font-weight: bold; }

.pos-list { display: flex; flex-direction: column; gap: 8px; }

.pos-card {
  background: #fff;
  border-radius: 10px;
  padding: 14px 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}

.pos-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.pos-title {
  font-size: 14px;
  font-weight: bold;
  color: #303133;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-right: 8px;
}

.sell-btn {
  padding: 6px 16px;
  background: #f56c6c;
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: bold;
  cursor: pointer;
  flex-shrink: 0;
}

.sell-btn:disabled { opacity: 0.6; }

.pos-detail {
  display: flex;
  gap: 16px;
}

.pos-item { display: flex; flex-direction: column; gap: 2px; }
.pos-label { font-size: 11px; color: #909399; }
.pos-val { font-size: 14px; font-weight: bold; color: #303133; }
.profit { color: #67c23a !important; }
.loss { color: #f56c6c !important; }

.empty-hint { text-align: center; color: #909399; padding: 40px 0; font-size: 14px; }
</style>
