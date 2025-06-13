Feature: Complete E2E Purchase Flow
  As a customer
  I want to purchase products
  So that I can receive them

  Background:
    Given I am on the home page

  @e2e @critical
  Scenario: Purchase a product as logged in user
    # Login
    When I click the "Sign In" link
    And I enter "testuser@example.com" in the "Email" field
    And I enter "Test@123" in the "Password" field
    And I click the "Login" button
    Then I should see "Welcome back"

    # Search and add to cart
    When I enter "MacBook Pro" in the search field
    And I click the search button
    Then I should see "Search Results"

    When I click the "MacBook Pro 16-inch" product
    Then I should see "Add to Cart"

    When I select "2" from the "Quantity" dropdown
    And I click the "Add to Cart" button
    Then I should see "Added to cart"

    # Checkout
    When I click the cart icon
    Then I should see "Shopping Cart"
    And I should see "MacBook Pro 16-inch"

    When I click the "Proceed to Checkout" button
    Then I should see "Shipping Information"

    # Fill shipping
    When I enter "John Doe" in the "Full Name" field
    And I enter "123 Test Street" in the "Address" field
    And I enter "New York" in the "City" field
    And I select "NY" from the "State" dropdown
    And I enter "10001" in the "ZIP Code" field
    And I click the "Continue" button

    # Payment
    Then I should see "Payment Information"
    When I enter "4111111111111111" in the "Card Number" field
    And I enter "12/25" in the "Expiry" field
    And I enter "123" in the "CVV" field
    And I click the "Place Order" button

    # Confirmation
    Then I should see "Order Confirmed"
    And I should see "Thank you for your order"
    And I take a screenshot "order_confirmation"