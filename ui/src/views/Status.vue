<template>
  <cv-grid fullWidth>
    <cv-row>
      <cv-column class="page-title">
        <h2>{{ $t("status.title") }}</h2>
      </cv-column>
    </cv-row>

    <cv-row v-if="error.load">
      <cv-column>
        <NsInlineNotification
          kind="error"
          :title="$t('status.title')"
          :description="error.load"
          :showCloseButton="false"
        />
      </cv-column>
    </cv-row>

    <cv-row>
      <cv-column :md="3" :max="3">
        <NsInfoCard
          light
          :title="configuration.internal_url || '-'"
          :description="$t('status.internal_url')"
          :loading="loading.load"
          :icon="launchIcon"
          class="min-height-card"
        />
      </cv-column>
      <cv-column :md="3" :max="3">
        <NsInfoCard
          light
          :title="configuration.node_id || '-'"
          :description="$t('status.node_id')"
          :loading="loading.load"
          :icon="chipIcon"
          class="min-height-card"
        />
      </cv-column>
      <cv-column :md="3" :max="3">
        <NsInfoCard
          light
          :title="
            configuration.same_node_only ? $t('common.yes') : $t('common.no')
          "
          :description="$t('status.same_node_only')"
          :loading="loading.load"
          :icon="lockedIcon"
          class="min-height-card"
        />
      </cv-column>
      <cv-column :md="3" :max="3">
        <NsInfoCard
          light
          :title="moduleStatus.index_status || '-'"
          :description="$t('status.index_status')"
          :loading="loading.load"
          :icon="activityIcon"
          class="min-height-card"
        />
      </cv-column>
    </cv-row>

    <cv-row>
      <cv-column :md="5" :max="5">
        <cv-tile light>
          <h4>{{ $t("status.sync_title") }}</h4>
          <div class="key-value-setting">
            <span class="label">{{ $t("status.sync_state") }}</span>
            <span class="value">{{ syncStatus.status || "-" }}</span>
          </div>
          <div class="key-value-setting">
            <span class="label">{{ $t("status.last_sync_at") }}</span>
            <span class="value">{{ moduleStatus.last_sync_at || "-" }}</span>
          </div>
          <div class="key-value-setting">
            <span class="label">{{ $t("status.last_successful_sync") }}</span>
            <span class="value">{{
              syncStatus.last_successful_sync_at || "-"
            }}</span>
          </div>
          <div class="button-row">
            <NsButton
              kind="secondary"
              :loading="loading.startSync"
              :disabled="loading.load || loading.startSync"
              @click="startSync"
            >
              {{ $t("status.start_sync") }}
            </NsButton>
            <NsButton kind="ghost" :disabled="loading.load" @click="refresh">
              {{ $t("status.refresh") }}
            </NsButton>
          </div>
        </cv-tile>
      </cv-column>
      <cv-column :md="7" :max="7">
        <cv-tile light>
          <h4>{{ $t("status.enabled_sources") }}</h4>
          <cv-structured-list v-if="enabledSources.length">
            <template slot="headings">
              <cv-structured-list-heading>
                {{ $t("status.source") }}
              </cv-structured-list-heading>
              <cv-structured-list-heading>
                {{ $t("status.instance") }}
              </cv-structured-list-heading>
            </template>
            <template slot="items">
              <cv-structured-list-item
                v-for="source in enabledSources"
                :key="source.name"
              >
                <cv-structured-list-data>{{
                  source.name
                }}</cv-structured-list-data>
                <cv-structured-list-data>{{
                  source.instance || "-"
                }}</cv-structured-list-data>
              </cv-structured-list-item>
            </template>
          </cv-structured-list>
          <NsEmptyState v-else :title="$t('status.no_enabled_sources')" />
        </cv-tile>
      </cv-column>
    </cv-row>

    <cv-row>
      <cv-column>
        <cv-tile light>
          <h4>{{ $t("status.token_title") }}</h4>
          <cv-structured-list v-if="tokenUsers.length">
            <template slot="headings">
              <cv-structured-list-heading>
                {{ $t("status.principal_id") }}
              </cv-structured-list-heading>
              <cv-structured-list-heading>
                {{ $t("status.username") }}
              </cv-structured-list-heading>
              <cv-structured-list-heading>
                {{ $t("status.token_enabled") }}
              </cv-structured-list-heading>
              <cv-structured-list-heading>
                {{ $t("status.last_used_at") }}
              </cv-structured-list-heading>
              <cv-structured-list-heading>
                {{ $t("status.actions") }}
              </cv-structured-list-heading>
            </template>
            <template slot="items">
              <cv-structured-list-item
                v-for="user in tokenUsers"
                :key="user.principal_id"
              >
                <cv-structured-list-data class="break-word">{{
                  user.principal_id
                }}</cv-structured-list-data>
                <cv-structured-list-data>{{
                  user.username
                }}</cv-structured-list-data>
                <cv-structured-list-data>
                  {{ user.enabled ? $t("common.yes") : $t("common.no") }}
                </cv-structured-list-data>
                <cv-structured-list-data>{{
                  user.last_used_at || "-"
                }}</cv-structured-list-data>
                <cv-structured-list-data>
                  <NsButton
                    kind="ghost"
                    :loading="loading.regenerating[user.principal_id]"
                    @click="regenerateUserToken(user.principal_id)"
                  >
                    {{ $t("status.regenerate_token") }}
                  </NsButton>
                </cv-structured-list-data>
              </cv-structured-list-item>
            </template>
          </cv-structured-list>
          <NsEmptyState v-else :title="$t('status.no_tokens')" />
        </cv-tile>
      </cv-column>
    </cv-row>
  </cv-grid>
</template>

<script>
import to from "await-to-js";
import { mapState } from "vuex";
import Launch32 from "@carbon/icons-vue/es/launch/32";
import Chip32 from "@carbon/icons-vue/es/chip/32";
import Locked32 from "@carbon/icons-vue/es/locked/32";
import Activity32 from "@carbon/icons-vue/es/activity/32";
import {
  QueryParamService,
  TaskService,
  UtilService,
  PageTitleService,
} from "@nethserver/ns8-ui-lib";

export default {
  name: "Status",
  mixins: [QueryParamService, TaskService, UtilService, PageTitleService],
  pageTitle() {
    return this.$t("status.title") + " - " + this.appName;
  },
  data() {
    return {
      q: {
        page: "status",
      },
      urlCheckInterval: null,
      configuration: {
        internal_url: "",
        node_id: "",
        same_node_only: true,
        sources: {},
      },
      launchIcon: Launch32,
      chipIcon: Chip32,
      lockedIcon: Locked32,
      activityIcon: Activity32,
      moduleStatus: {
        index_status: "-",
        last_sync_at: null,
      },
      tokenUsers: [],
      syncStatus: {},
      loading: {
        load: false,
        startSync: false,
        regenerating: {},
      },
      error: {
        load: "",
      },
    };
  },
  computed: {
    ...mapState(["instanceName", "core", "appName"]),
    enabledSources() {
      return Object.entries(this.configuration.sources || {})
        .filter(([, value]) => value.enabled)
        .map(([name, value]) => ({ name, instance: value.instance }));
    },
  },
  beforeRouteEnter(to, from, next) {
    next((vm) => {
      vm.watchQueryData(vm);
      vm.urlCheckInterval = vm.initUrlBindingForApp(vm, vm.q.page);
    });
  },
  beforeRouteLeave(to, from, next) {
    clearInterval(this.urlCheckInterval);
    next();
  },
  created() {
    this.refresh();
  },
  methods: {
    async runModuleAction(action, { data = {}, onComplete, onAborted } = {}) {
      const eventId = this.getUuid();
      this.core.$root.$once(
        `${action}-completed-${eventId}`,
        (taskContext, taskResult) =>
          onComplete && onComplete(taskContext, taskResult)
      );
      this.core.$root.$once(
        `${action}-aborted-${eventId}`,
        (taskResult, taskContext) =>
          onAborted && onAborted(taskResult, taskContext)
      );

      const res = await to(
        this.createModuleTaskForApp(this.instanceName, {
          action,
          data,
          extra: {
            title: this.$t(`action.${action}`),
            isNotificationHidden: true,
            eventId,
          },
        })
      );
      return res[0];
    },
    async refresh() {
      this.loading.load = true;
      this.error.load = "";

      const configurationError = await this.runModuleAction(
        "get-configuration",
        {
          onComplete: (taskContext, taskResult) => {
            const output = taskResult.output;
            this.configuration = output.configuration || {};
            this.moduleStatus = output.status || {};
            this.tokenUsers = output.tokens?.users || [];
          },
        }
      );

      if (configurationError) {
        this.error.load = this.getErrorMessage(configurationError);
        this.loading.load = false;
        return;
      }

      const syncError = await this.runModuleAction("get-sync-status", {
        onComplete: (taskContext, taskResult) => {
          this.syncStatus = taskResult.output || {};
          this.loading.load = false;
        },
        onAborted: () => {
          this.error.load = this.$t("error.generic_error");
          this.loading.load = false;
        },
      });

      if (syncError) {
        this.error.load = this.getErrorMessage(syncError);
        this.loading.load = false;
      }
    },
    async startSync() {
      this.loading.startSync = true;
      const error = await this.runModuleAction("start-sync", {
        onComplete: () => {
          this.loading.startSync = false;
          this.refresh();
        },
        onAborted: () => {
          this.loading.startSync = false;
        },
      });

      if (error) {
        this.loading.startSync = false;
        this.error.load = this.getErrorMessage(error);
      }
    },
    async regenerateUserToken(principalId) {
      this.$set(this.loading.regenerating, principalId, true);
      const error = await this.runModuleAction("regenerate-user-token", {
        data: { principal_id: principalId },
        onComplete: () => {
          this.$set(this.loading.regenerating, principalId, false);
          this.refresh();
        },
        onAborted: () => {
          this.$set(this.loading.regenerating, principalId, false);
        },
      });

      if (error) {
        this.$set(this.loading.regenerating, principalId, false);
        this.error.load = this.getErrorMessage(error);
      }
    },
  },
};
</script>

<style scoped lang="scss">
.button-row {
  display: flex;
  gap: 1rem;
  margin-top: 1.5rem;
}

.break-word {
  word-break: break-word;
}
</style>
