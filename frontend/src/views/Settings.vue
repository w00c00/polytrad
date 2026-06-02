<template>
  <div>
    <el-row :gutter="20">
      <el-col :span="12">
        <el-card>
          <template #header>修改密码</template>
          <el-form label-position="top" size="small">
            <el-form-item label="原密码">
              <el-input v-model="pwdForm.old_password" type="password" show-password />
            </el-form-item>
            <el-form-item label="新密码">
              <el-input v-model="pwdForm.new_password" type="password" show-password placeholder="至少 6 位" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="pwdLoading" @click="changePwd">修改密码</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card>
          <template #header>钱包管理</template>
          <el-form label-position="top" size="small">
            <el-form-item label="私钥 (MetaMask)">
              <el-input v-model="walletForm.private_key" type="password" show-password placeholder="0x..." />
            </el-form-item>
            <el-form-item>
              <template #label>
                <span>Funder 地址</span>
                <el-tooltip content="EOA 可留空。Proxy/Safe/Deposit 模式必须填写 Polymarket 实际持有资金的钱包地址。" placement="top">
                  <el-icon style="margin-left:4px;cursor:pointer"><QuestionFilled /></el-icon>
                </el-tooltip>
              </template>
              <el-input v-model="walletForm.funder_address" placeholder="EOA 留空；Proxy/Safe/Deposit 填资金地址" />
            </el-form-item>
            <el-form-item label="签名类型">
              <el-select v-model="walletForm.signature_type" style="width:100%">
                <el-option v-for="item in signatureTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
              <el-text size="small" type="info" style="margin-top:6px;display:block">
                普通私钥钱包选 EOA；Polymarket Deposit 钱包通常选 Deposit/1271。
              </el-text>
            </el-form-item>
            <el-form-item label="链 ID">
              <el-radio-group v-model="walletForm.chain_id">
                <el-radio :value="137">主网 (137)</el-radio>
                <el-radio :value="80002">测试网 (80002)</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="walletLoading" @click="setupWallet">配置钱包</el-button>
            </el-form-item>
          </el-form>

          <el-divider>已有钱包</el-divider>
          <el-table :data="wallets" size="small">
            <el-table-column prop="wallet_address" label="地址" show-overflow-tooltip />
            <el-table-column label="签名" width="120">
              <template #default="{ row }">{{ signatureTypeLabel(row.signature_type) }}</template>
            </el-table-column>
            <el-table-column prop="chain_id" label="链" width="80" />
            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '活跃' : '停用' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="180">
              <template #default="{ row }">
                <el-button v-if="row.is_active" size="small" type="warning" @click="deactivate(row.id)">停用</el-button>
                <el-button v-else size="small" type="success" @click="activate(row.id)">启用</el-button>
                <el-button size="small" type="danger" link @click="removeWallet(row.id)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card>
          <template #header>推送通知</template>
          <el-tabs v-model="notifyTab">
            <el-tab-pane label="方糖" name="serverchan">
              <el-form label-position="top" size="small">
                <el-form-item label="SendKey">
                  <el-input v-model="scForm.sendkey" placeholder="方糖 SendKey" />
                </el-form-item>
                <el-form-item>
                  <el-button type="primary" @click="saveNotify('serverchan')">保存</el-button>
                  <el-button @click="testNotify('serverchan')">测试</el-button>
                </el-form-item>
              </el-form>
            </el-tab-pane>
            <el-tab-pane label="Telegram" name="telegram">
              <el-form label-position="top" size="small">
                <el-form-item label="Bot Token">
                  <el-input v-model="tgForm.bot_token" placeholder="123456:ABC-DEF..." />
                </el-form-item>
                <el-form-item label="Chat ID">
                  <el-input v-model="tgForm.chat_id" placeholder="Chat ID" />
                </el-form-item>
                <el-form-item>
                  <el-button type="primary" @click="saveNotify('telegram')">保存</el-button>
                  <el-button @click="testNotify('telegram')">测试</el-button>
                </el-form-item>
              </el-form>
            </el-tab-pane>
          </el-tabs>

          <el-divider>手动推送</el-divider>
          <el-button size="small" type="success" :loading="pushLoading" @click="pushTradeReport" style="margin-bottom:12px">
            推送交易报告
          </el-button>
          <el-text size="small" type="info" style="display:block;margin-bottom:12px">手动推送当前持仓和最近交易到已配置的推送渠道</el-text>

          <el-divider>已配置</el-divider>
          <el-table :data="notifyConfigs" size="small">
            <el-table-column prop="channel" label="渠道" width="100" />
            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '启用' : '停用' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="80">
              <template #default="{ row }">
                <el-button size="small" type="danger" link @click="deleteNotify(row.id)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { walletApi, notifyApi, authApi } from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { QuestionFilled } from '@element-plus/icons-vue'

const walletLoading = ref(false)
const wallets = ref<any[]>([])
const notifyConfigs = ref<any[]>([])
const notifyTab = ref('serverchan')

const signatureTypeOptions = [
  { value: 0, label: 'EOA (0)' },
  { value: 1, label: 'Proxy (1)' },
  { value: 2, label: 'Safe (2)' },
  { value: 3, label: 'Deposit/1271 (3)' },
]

const walletForm = reactive({ private_key: '', funder_address: '', chain_id: 137, signature_type: 0 })
const scForm = reactive({ sendkey: '' })
const tgForm = reactive({ bot_token: '', chat_id: '' })
const pwdForm = reactive({ old_password: '', new_password: '' })
const pwdLoading = ref(false)
const pushLoading = ref(false)

async function changePwd() {
  if (!pwdForm.old_password || !pwdForm.new_password) { ElMessage.warning('请填写完整'); return }
  if (pwdForm.new_password.length < 6) { ElMessage.warning('新密码至少 6 位'); return }
  pwdLoading.value = true
  try {
    await authApi.changePassword(pwdForm)
    ElMessage.success('密码修改成功')
    pwdForm.old_password = ''
    pwdForm.new_password = ''
  } catch {} finally { pwdLoading.value = false }
}

async function setupWallet() {
  if (walletForm.signature_type > 0 && !walletForm.funder_address.trim()) {
    ElMessage.warning('Proxy/Safe/Deposit 钱包必须填写 Funder 地址')
    return
  }
  walletLoading.value = true
  try {
    await walletApi.setup({
      private_key: walletForm.private_key,
      funder_address: walletForm.signature_type === 0 ? '' : walletForm.funder_address.trim(),
      chain_id: walletForm.chain_id,
      signature_type: walletForm.signature_type,
    })
    ElMessage.success('钱包配置成功')
    walletForm.private_key = ''
    loadWallets()
  } catch {} finally { walletLoading.value = false }
}

function signatureTypeLabel(value: number | string | null | undefined) {
  const type = Number(value || 0)
  return signatureTypeOptions.find((item) => item.value === type)?.label || `未知(${type})`
}

async function loadWallets() {
  try {
    const { data } = await walletApi.list()
    wallets.value = data
  } catch {}
}

async function deactivate(id: number) {
  await walletApi.deactivate(id)
  loadWallets()
}

async function activate(id: number) {
  await walletApi.activate(id)
  loadWallets()
}

async function removeWallet(id: number) {
  try {
    await ElMessageBox.confirm('确认删除该钱包配置？', '警告', { type: 'warning' })
    await walletApi.delete(id)
    ElMessage.success('已删除')
    loadWallets()
  } catch {}
}

async function saveNotify(channel: string) {
  const config = channel === 'serverchan' ? { sendkey: scForm.sendkey } : { bot_token: tgForm.bot_token, chat_id: tgForm.chat_id }
  try {
    await notifyApi.saveConfig({ channel, config })
    ElMessage.success('推送配置已保存')
    loadNotifyConfigs()
  } catch {}
}

async function testNotify(channel: string) {
  try {
    await notifyApi.test({ channel })
    ElMessage.success('测试消息已发送')
  } catch {}
}

async function loadNotifyConfigs() {
  try {
    const { data } = await notifyApi.getConfig()
    notifyConfigs.value = data
  } catch {}
}

async function deleteNotify(id: number) {
  await notifyApi.deleteConfig(id)
  loadNotifyConfigs()
}

async function pushTradeReport() {
  pushLoading.value = true
  try {
    const { data } = await notifyApi.tradeReport()
    ElMessage.success(data.message || '交易报告已推送')
  } catch {} finally { pushLoading.value = false }
}

onMounted(() => {
  loadWallets()
  loadNotifyConfigs()
})
</script>
