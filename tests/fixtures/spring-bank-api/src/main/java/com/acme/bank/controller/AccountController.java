package com.acme.bank.controller;

import com.acme.bank.model.Account;
import com.acme.bank.repository.AccountRepository;
import com.acme.bank.service.TransferService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@CrossOrigin("*")
@RequestMapping("/accounts")
public class AccountController {

    @Autowired
    private AccountRepository accounts;

    @Autowired
    private TransferService transferService;

    @GetMapping("/{id}")
    public Account get(@PathVariable Long id) {
        return accounts.findById(id).orElse(null);
    }

    @GetMapping("/search")
    public List<Account> search(@RequestParam String owner) {
        return accounts.searchByOwner(owner);
    }

    @GetMapping
    public List<Account> all() {
        return accounts.findAll();
    }

    @PostMapping("/transfer")
    public ResponseEntity<?> transfer(@RequestBody Map<String, Object> body) {
        try {
            Long from = Long.valueOf(body.get("from").toString());
            Long to = Long.valueOf(body.get("to").toString());
            double amount = Double.parseDouble(body.get("amount").toString());
            transferService.transfer(from, to, amount);
            return ResponseEntity.ok(Map.of("status", "ok"));
        } catch (Exception e) {
            e.printStackTrace();
            return ResponseEntity.ok(Map.of("status", "error", "message", e.toString()));
        }
    }
}
