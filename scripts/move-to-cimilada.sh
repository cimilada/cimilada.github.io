#!/bin/sh
# Move the site to https://cimilada.github.io/ once the free GitHub organization "cimilada" exists
# (create it at https://github.com/organizations/plan, Free plan). Run from the repository root.
set -e
OLD=mustafah1/somalia-weather-dashboard
NEW=cimilada/cimilada.github.io
SITE=https://cimilada.github.io/

gh api orgs/cimilada --jq .login >/dev/null || { echo "Create the cimilada organization first"; exit 1; }

# A repository named <org>.github.io is served at the organization's root address.
gh api -X POST "repos/$OLD/transfer" -f new_owner=cimilada -f new_name=cimilada.github.io >/dev/null
echo "transfer requested; waiting for GitHub to finish it"
until gh api "repos/$NEW" --jq .full_name >/dev/null 2>&1; do sleep 5; done

gh api -X POST "repos/$NEW/pages" -f build_type=workflow >/dev/null 2>&1 \
  || gh api -X PUT "repos/$NEW/pages" -f build_type=workflow >/dev/null
gh variable set SITE_URL --body "$SITE" --repo "$NEW"
gh repo edit "$NEW" --homepage "$SITE"
git remote set-url origin "https://github.com/$NEW.git"

# point the README at the new address and redeploy
sed -i.bak "s#https://mustafah1.github.io/somalia-weather-dashboard/#$SITE#g" README.md && rm -f README.md.bak
sed -i.bak "s#mustafah1/somalia-weather-dashboard#$NEW#g" build.py && rm -f build.py.bak
git add README.md build.py
git commit -m "Move to $SITE" && git push
echo "Deploying; the site will be live at $SITE in about 30 minutes."
