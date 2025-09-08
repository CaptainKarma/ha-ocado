# configuration.yaml
# include email account where Ocado order emails are sent
sensor:
  - platform: ocado
    email: x@x.x.uk
    password: pwd
    imap_server: mail.x.x.uk
    imap_port: 587
    ssl: true
    days_old: 7




# Mushroom template card examples

type: custom:mushroom-template-card
primary: Edit Order Until
secondary: >
  {{ state_attr('sensor.ocado_tracking', 'edit_until_date') | default('N/A') }}
  {{ state_attr('sensor.ocado_tracking', 'edit_until_time') | default('N/A') }}
icon: mdi:note-edit
multiline_secondary: true
tap_action:
  action: none
hold_action:
  action: none
double_tap_action:
  action: none
fill_container: false
icon_color: blue

type: custom:mushroom-template-card
primary: Delivery Scheduled
secondary: >
  {{ state_attr('sensor.ocado_tracking', 'delivery_date') | default('N/A') }} {{
  state_attr('sensor.ocado_tracking', 'delivery_time') | default('N/A') }}
icon: mdi:truck
multiline_secondary: true
tap_action:
  action: none
hold_action:
  action: none
double_tap_action:
  action: none
fill_container: false
icon_color: blue


# Example Automation when Edit Order is closing soon, Pushbullet, TV Notification and TTS to Media Player

alias: Ocado Edit Order
description: ""
triggers:
  - entity_id:
      - sensor.ocado_tracking
    attribute: edit_countdown
    below: 60
    above: 45
    trigger: numeric_state
conditions: []
actions:
  - data:
      title: Order Editing Closing Soon
      target: device/SM-S926B
      message: Ocado Alert
    action: notify.push_bullet
  - metadata: {}
    data:
      skip_condition: true
    target:
      entity_id: automation.tv_notify_test
    action: automation.trigger
  - data:
      media_player_entity_id: media_player.kitchen
      message: >
        Your Ocado shopping order is closing shortly in {{
        state_attr('sensor.ocado_tracking', 'Edit Countdown Minutes') }}
        minutes, at {{ state_attr('sensor.ocado_tracking', 'Edit Until Time')
        }}.
      cache: false
    target:
      entity_id: tts.home_assistant_cloud
    action: tts.speak
mode: single

