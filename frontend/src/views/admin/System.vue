<template>
  <div>
    <el-row :gutter="20">
      <el-col :span="12">
        <el-card>
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>AI 模型配置</span>
              <el-button size="small" type="primary" @click="showAddAI = true">添加</el-button>
            </div>
          </template>
          <el-table :data="aiConfigs" size="small">
            <el-table-column prop="name" label="名称" width="120" />
            <el-table-column prop="provider" label="提供商" width="100" />
            <el-table-column prop="model_name" label="模型" />
            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '启用' : '停用' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="100">
              <template #default="{ row }">
                <el-button size="small" type="danger" link @click="deleteAI(row.id)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card>
          <template #header>系统操作</template>
          <el-space direction="vertical" :size="16" alignment="stretch" style="width:100%">
            <el-button type="warning" @click="restart" :loading="restarting">重启服务</el-button>
          </el-space>
        </el-card>
      </el-col>
    </el-row>

    <el-dialog v-model="showAddAI" title="添加 AI 模型" width="500">
      <el-form label-position="top" size="small">
        <el-form-item label="名称">
          <el-input v-model="aiForm.name" placeholder="如: OpenRouter GPT-4o" />
        </el-form-item>
        <el-form-item label="提供商">
          <el-select v-model="aiForm.provider" style="width:100%">
            <el-option label="Minimax" value="minimax" />
            <el-option label="OpenRouter" value="openrouter" />
            <el-option label="GLM 智谱" value="glm" />
            <el-option label="火山引擎" value="volcano" />
            <el-option label="自定义" value="custom" />
          </el-select>
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="aiForm.api_key" type="password" show-password />
        </el-form-item>
        <el-form-item label="模型名称">
          <el-input v-model="aiForm.model_name" placeholder="如 gpt-4o, glm-4" />
        </el-form-item>
        <el-form-item v-if="aiForm.provider === 'custom'" label="Base URL">
          <el-input v-model="aiForm.base_url" placeholder="https://your-api.com/v1" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddAI = false">取消</el-button>
        <el-button type="primary" @click="addAI">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { adminApi } from '../../api'
import { ElMessage, ElMessageBox } from 'element-plus'

const aiConfigs = ref<any[]>([])
const showAddAI = ref(false)
const restarting = ref(false)
const aiForm = reactive({ name: '', provider: 'openrouter', api_key: '', model_name: '', base_url: '' })

async function loadAI() {
  try {
    const { data } = await adminApi.getAIConfigs()
    aiConfigs.value = data
  } catch {}
}

async function addAI() {
  try {
    await adminApi.createAIConfig(aiForm)
    ElMessage.success('AI 模型已添加')
    showAddAI.value = false
    Object.assign(aiForm, { name: '', api_key: '', model_name: '', base_url: '' })
    loadAI()
  } catch {}
}

async function deleteAI(id: number) {
  await ElMessageBox.confirm('确认删除？')
  await adminApi.deleteAIConfig(id)
  ElMessage.success('已删除')
  loadAI()
}

async function restart() {
  await ElMessageBox.confirm('确认重启服务？', '警告', { type: 'warning' })
  restarting.value = true
  try {
    await adminApi.restart()
    ElMessage.success('重启信号已发送')
  } catch {} finally { restarting.value = false }
}

onMounted(loadAI)
</script>
