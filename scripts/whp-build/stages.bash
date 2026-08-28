# Retired WHP build-stage loader.
#
# builder.sh now owns both module loading and execution order so there is only
# one production orchestration list to maintain.  This tombstone is kept
# temporarily because the repository write interface could not remove the path
# directly; it intentionally defines and loads nothing.
