<!--
  Copyright (C) 2023 Nethesis S.r.l.
  SPDX-License-Identifier: GPL-3.0-or-later
-->
<template>
  <div id="ns8-app">
    <cv-content id="main-content" class="app-content">
      <AppSideMenu />
      <AppMobileSideMenu />
      <router-view />
    </cv-content>
  </div>
</template>

<script>
import AppSideMenu from "./components/AppSideMenu";
import AppMobileSideMenu from "./components/AppMobileSideMenu";
import { mapState, mapActions } from "vuex";
import { QueryParamService, UtilService } from "@nethserver/ns8-ui-lib";

export default {
  name: "App",
  components: { AppSideMenu, AppMobileSideMenu },
  mixins: [QueryParamService, UtilService],
  computed: {
    ...mapState(["instanceName", "instanceLabel", "core"]),
  },
  created() {
    const core = window.parent.core;
    this.setCoreInStore(core);
    const instanceName = /#\/apps\/([a-zA-Z0-9_-]+)/.exec(
      window.parent.location.hash
    )[1];
    this.setInstanceNameInStore(instanceName);
    this.setInstanceLabelInStore(instanceName);
    this.setAppName();

    // listen to change route events
    const context = this;
    window.addEventListener(
      "changeRoute",
      function (e) {
        const requestedPage = e.detail;
        context.$router.replace(requestedPage);
      },
      false
    );

    // configure global shortcuts
    core.$root.$emit("configureKeyboardShortcuts", window);

    const queryParams = this.getQueryParamsForApp();
    const requestedPage = queryParams.page || "status";

    if (requestedPage != "status") {
      this.$router.replace(requestedPage);
    }
  },
  methods: {
    ...mapActions([
      "setInstanceNameInStore",
      "setInstanceLabelInStore",
      "setCoreInStore",
      "setAppNameInStore",
    ]),
    setAppName() {
      const metadata = require("../public/metadata.json");
      const appName = metadata.name;
      this.setAppNameInStore(appName);
    },
  },
};
</script>

<style lang="scss">
@import "styles/carbon-utils";
</style>
